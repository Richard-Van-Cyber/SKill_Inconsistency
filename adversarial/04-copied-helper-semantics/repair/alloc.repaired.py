# Minimal repair of the helper SKILL.md tells the agent to copy.
# The call site already asks for these bounds; the body just has to honour them.
offset = {}
n = 0
bounds = {}          # index -> (lb, ub)
integrality = {}     # index -> 0/1


def alloc(name, shape, lb=0.0, ub=float("inf"), integer=False):
    global n
    size = int(np.prod(shape))
    idx = np.arange(n, n + size).reshape(shape)
    offset[name] = idx
    for j in np.asarray(idx).ravel():
        bounds[int(j)] = (float(lb), float(ub))
        integrality[int(j)] = 1 if integer else 0
    n += size
    return idx
