"""Credential-only HTTP forwarding. Does not implement an agent or convert protocols."""

import datetime
import hashlib
import http.client
import http.server
import json
import secrets
import threading
import time
import urllib.parse

# Per-run API budget enforced by this proxy. Raised for the directed-repair
# study (was 60 / 1_000_000 / 32_768), which truncated 23 of 90 primary-study
# runs, including every fix-druid / fix-erlang cell. Routing, credential
# handling and usage parsing below are unchanged.
API_BUDGET_GENERATION_REQUESTS = 60
API_BUDGET_CUMULATIVE_TOKENS = 1_000_000
API_BUDGET_OUTPUT_TOKENS = 32_768


class CredentialProxy:
    def __init__(self, key, group, model, output, bind='172.17.0.1'):
        self.key, self.group, self.model, self.output = key, group, model, output
        self.token = secrets.token_urlsafe(32)
        self.calls = 0
        self.input_tokens = self.output_tokens = 0
        self.observed_models = set()
        self.lock = threading.Lock()
        self.stop_reason = None
        outer = self

        class Handler(http.server.BaseHTTPRequestHandler):
            protocol_version = 'HTTP/1.1'

            def log_message(self, *args):
                pass

            def do_POST(self):
                prefix = '/' + outer.token
                path = self.path[len(prefix):] if self.path.startswith(prefix + '/') else ''
                allowed = ['/v1/messages', '/v1/messages/count_tokens'] if outer.group == 'claude' else ['/v1/responses']
                if urllib.parse.urlsplit(path).path not in allowed:
                    self.send_error(403, 'Route unavailable')
                    return
                size = int(self.headers.get('Content-Length', '0'))
                if not 0 < size <= 33554432:
                    self.send_error(413)
                    return
                body = self.rfile.read(size)
                try:
                    payload = json.loads(body)
                except ValueError:
                    self.send_error(400)
                    return
                if payload.get('model') != outer.model:
                    self.send_error(400, 'Experiment model is fixed')
                    return
                generation = not path.startswith('/v1/messages/count_tokens')
                with outer.lock:
                    if generation and (outer.calls >= API_BUDGET_GENERATION_REQUESTS
                                       or outer.input_tokens + outer.output_tokens >= API_BUDGET_CUMULATIVE_TOKENS
                                       or outer.output_tokens >= API_BUDGET_OUTPUT_TOKENS):
                        outer.stop_reason = 'api_budget'
                        self.send_error(429, 'Experiment API budget reached')
                        return
                    if generation:
                        outer.calls += 1
                    serial = secrets.token_hex(5)
                headers = {'Content-Type': 'application/json', 'Accept-Encoding': 'identity'}
                for name in ['anthropic-version', 'anthropic-beta', 'accept', 'user-agent', 'openai-beta']:
                    if self.headers.get(name):
                        headers[name] = self.headers[name]
                if outer.group == 'claude':
                    headers['x-api-key'] = outer.key
                else:
                    headers['Authorization'] = 'Bearer ' + outer.key
                conn = http.client.HTTPSConnection('penguinapi.vip', timeout=180)
                captured = bytearray()
                code, error = None, None
                began = False
                timer = time.monotonic()
                record = {'at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
                          'path': path, 'model': payload.get('model'), 'stream': payload.get('stream'),
                          'request_sha256': hashlib.sha256(body).hexdigest(), 'request_bytes': size,
                          'generation': generation, 'id': serial}
                # No authorization headers are persisted. Body is CLI-produced task content.
                (outer.output / ('request-' + serial + '.json')).write_bytes(body)
                try:
                    conn.request('POST', path, body=body, headers=headers)
                    response = conn.getresponse()
                    code = response.status
                    self.send_response(code)
                    self.send_header('Content-Type', response.getheader('Content-Type', 'application/json'))
                    self.send_header('Connection', 'close')
                    self.end_headers()
                    began = True
                    while True:
                        chunk = response.read1(65536)
                        if not chunk:
                            break
                        captured.extend(chunk)
                        self.wfile.write(chunk)
                        self.wfile.flush()
                except Exception as exc:
                    error = type(exc).__name__ + ': ' + str(exc).replace(outer.key, '[REDACTED]')
                    if not began:
                        self.send_error(502, 'Upstream connection failed')
                finally:
                    conn.close()
                    self.close_connection = True
                    data = bytes(captured)
                    (outer.output / ('response-' + serial + '.txt')).write_bytes(data)
                    usage, models = outer.parse_usage(data)
                    with outer.lock:
                        outer.input_tokens += usage['input_tokens']
                        outer.output_tokens += usage['output_tokens']
                        outer.observed_models.update(models)
                        record.update(status=code, error=error, usage=usage, observed_models=sorted(models), duration_seconds=round(time.monotonic()-timer, 4))
                        with (outer.output / 'requests.jsonl').open('a') as f:
                            f.write(json.dumps(record) + '\n')

        self.server = http.server.ThreadingHTTPServer((bind, 0), Handler)
        self.server.daemon_threads = True
        self.url = f'http://{bind}:{self.server.server_port}/{self.token}'
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    @staticmethod
    def parse_usage(data):
        objects = []
        try:
            objects.append(json.loads(data))
        except (ValueError, UnicodeDecodeError):
            for line in data.splitlines():
                if line.startswith(b'data: '):
                    try:
                        objects.append(json.loads(line[6:]))
                    except ValueError:
                        pass
        final_usage = {}
        models = set()
        for obj in objects:
            message = obj.get('message') or obj.get('response') or obj
            if message.get('model'):
                models.add(message['model'])
            usage = message.get('usage') or obj.get('usage') or {}
            # Relay final events may revise cache categories downward; last reported fields win.
            for key in ['input_tokens', 'cache_creation_input_tokens', 'cache_read_input_tokens', 'output_tokens']:
                if key in usage: final_usage[key] = int(usage[key] or 0)
        ins = sum(final_usage.get(k, 0) for k in ['input_tokens', 'cache_creation_input_tokens', 'cache_read_input_tokens'])
        return {'input_tokens': ins, 'output_tokens': final_usage.get('output_tokens', 0)}, models

    def start(self):
        self.thread.start()

    def stop(self):
        self.server.shutdown()
        self.server.server_close()

