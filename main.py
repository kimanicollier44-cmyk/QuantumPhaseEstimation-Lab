#!/usr/bin/env python3
"""QuantumPhaseEstimation-Lab - educational quantum phase estimation lab.

by Darion Kellar

Pure Python standard library. Zero dependencies. Zero network.
Education only - and the central lesson is stated up front:

  * Quantum phase estimation (QPE) reads out the eigenphase theta of
    a unitary U from the phase kickback it leaves on a counting
    register, sharpened by an inverse quantum Fourier transform.
  * This lab builds the whole circuit from scratch on a classical
    statevector simulator: controlled-U^(2^k) as exact matrix powers,
    an inverse QFT assembled from Hadamards, controlled phases, and
    swaps, and outcome probabilities read directly off the final
    statevector - no sampling, no hidden randomness.
  * When theta sits exactly on the 2^t grid, the answer is a delta
    function: probability 1 on one outcome, and the lab shows why.
    When theta sits off the grid, the peak probability follows the
    Dirichlet kernel P = (1/2^(2t)) * sin^2(2^t * pi * delta) /
    sin^2(pi * delta), and the simulator is graded against that
    formula to ~1e-15.
  * Every accuracy claim is printed next to its cost: t counting
    qubits buy a grid spacing of 2^-t and cost 2^t - 1 controlled-U
    applications. Precision is a ledger, not a slogan.

The simulator is classical and pays 2^n amplitudes for n qubits
(512 amplitudes at t = 8). No molecule's energy was computed here,
no quantum hardware ran, and no speedup over anything is claimed.
Chemistry, hardware, cryptography, and production-solver uses are
permanent HOLD gates - with Gemini Argon 4 Extended Thinking as
DECIDER (names-only, tighten-only), Muse as advisor (never
overrides HOLD), and Google Flow plan-only seats.
"""
import cmath
import hashlib
import json
import math
import sys

# ---------------------------------------------------------------- constants
VERSION = "1.0.0"

# Labelled teaching values. The phases, the rotation angle, and the
# time scale below are chosen so the arithmetic can be checked by
# hand - they are not measurements of anything.
THETA_SWEEP = 0.3            # off-grid phase used across the sweep tables
THETA_EXACT_NUM = 13         # exact case: theta = 13/32 at t = 5
ROTATION_ALPHA = 0.7         # labelled rotation angle (radians)
TAU = 0.5                    # labelled phase-to-energy time scale

# ---------------------------------------------------------------- HOLD gates
HOLD_GATES = {
    "molecular_energy_claim": "HOLD - no real molecular or electronic energies; the unitaries here are labelled toys",
    "quantum_hardware_run_claim": "HOLD - nothing in this lab ran on quantum hardware; it is a classical statevector simulator",
    "quantum_speedup_claim": "HOLD - the simulator pays 2^n amplitudes; no speedup over any method is demonstrated or claimed",
    "cryptographic_use": "HOLD - no use against real cryptographic keys, systems, or protocols",
    "drug_discovery_claim": "HOLD - no drug-discovery, docking, or pharmaceutical claim from a toy phase readout",
    "materials_design_claim": "HOLD - no materials design or property prediction from labelled unitaries",
    "production_solver_claim": "HOLD - no production eigenvalue, linear-algebra, or simulation service",
    "benchmark_superiority_claim": "HOLD - no benchmark or superiority claim against real QPUs or software",
    "financial_model_claim": "HOLD - no financial risk, pricing, or portfolio model use",
    "machine_learning_speedup_claim": "HOLD - no machine-learning speedup or advantage claim",
    "certified_precision_claim": "HOLD - no certified precision for any real-world quantity; error bars here describe a grid",
    "hardware_control_use": "HOLD - no controlling, calibrating, or characterising real quantum hardware",
    "sensor_calibration_claim": "HOLD - no calibrating real sensors or clocks from simulated phases",
    "independent_verification_claim": "HOLD - simulator output is not independent verification of any published result",
}


def gate(action):
    """Return 'HOLD' if the action is gated, else 'PROCEED' (sandbox sim)."""
    return "HOLD" if action in HOLD_GATES else "PROCEED"


# ================================================================ 1. Statevector simulator
# Qubit q is bit q of the state index. Counting qubits are 0..t-1
# (counting qubit k controls U^(2^k) and ends up as bit k of the
# measured integer); the target qubit is bit t. Gates are applied by
# index arithmetic on the amplitude list - no library does the work.

_SQRT2 = math.sqrt(2.0)
H_GATE = [[1.0 / _SQRT2, 1.0 / _SQRT2], [1.0 / _SQRT2, -1.0 / _SQRT2]]


def apply_single(state, qubit, matrix):
    step = 1 << qubit
    for base in range(0, len(state), step * 2):
        for off in range(step):
            i0 = base + off
            i1 = i0 + step
            a, b = state[i0], state[i1]
            state[i0] = matrix[0][0] * a + matrix[0][1] * b
            state[i1] = matrix[1][0] * a + matrix[1][1] * b


def apply_controlled(state, control, target, matrix):
    bc, bt = 1 << control, 1 << target
    for i in range(len(state)):
        if (i & bc) and not (i & bt):
            j = i | bt
            a, b = state[i], state[j]
            state[i] = matrix[0][0] * a + matrix[0][1] * b
            state[j] = matrix[1][0] * a + matrix[1][1] * b


def apply_cphase(state, control, target, angle):
    bc, bt = 1 << control, 1 << target
    phase = cmath.exp(1j * angle)
    for i in range(len(state)):
        if (i & bc) and (i & bt):
            state[i] *= phase


def apply_swap(state, qa, qb):
    ba, bb = 1 << qa, 1 << qb
    for i in range(len(state)):
        if not (i & ba) and (i & bb):
            j = i ^ (ba | bb)
            state[i], state[j] = state[j], state[i]


def qft_ops(t):
    """Gate list for the forward QFT on counting qubits 0..t-1.

    Processed most-significant qubit first (H, then controlled
    phases from the lower qubits), swaps last. Verified in CHECKS
    against the direct DFT definition: this circuit maps |x> to
    (1/sqrt(2^t)) * sum_y exp(+2 pi i x y / 2^t) |y>, and its
    reverse with negated angles is the inverse QFT.
    """
    ops = []
    for k in range(t - 1, -1, -1):
        ops.append(("H", k))
        for j in range(k - 1, -1, -1):
            ops.append(("CP", j, k, 2.0 * math.pi / (2 ** (k - j + 1))))
    for k in range(t // 2):
        ops.append(("SW", k, t - 1 - k))
    return ops


def apply_qft(state, t, inverse=False):
    ops = qft_ops(t)
    if inverse:
        ops = ops[::-1]
    for op in ops:
        if op[0] == "H":
            apply_single(state, op[1], H_GATE)
        elif op[0] == "CP":
            angle = -op[3] if inverse else op[3]
            apply_cphase(state, op[1], op[2], angle)
        else:
            apply_swap(state, op[1], op[2])


def mat_mul(a, b):
    return [
        [a[0][0] * b[0][0] + a[0][1] * b[1][0],
         a[0][0] * b[0][1] + a[0][1] * b[1][1]],
        [a[1][0] * b[0][0] + a[1][1] * b[1][0],
         a[1][0] * b[0][1] + a[1][1] * b[1][1]],
    ]


def mat_pow2(matrix, k):
    """matrix^(2^k) by repeated squaring - exact, no eigensolver."""
    result = matrix
    for _ in range(k):
        result = mat_mul(result, result)
    return result


# ================================================================ 2. Unitaries + QPE circuit
def phase_unitary(theta):
    """U = diag(1, exp(2 pi i theta)); eigenstate |1>, eigenphase theta."""
    return [[1.0, 0.0], [0.0, cmath.exp(2j * math.pi * theta)]]


def rotation_unitary(alpha):
    """Real rotation by alpha; eigenvalues exp(+-i alpha)."""
    c, s = math.cos(alpha), math.sin(alpha)
    return [[c, -s], [s, c]]


def eigenphase_from_trace(matrix):
    """Eigenphase theta in [0, 1/2] of a 2x2 rotation from its trace.

    trace = 2 cos(alpha), so alpha = arccos(trace / 2) and the
    eigenphase of the exp(+i alpha) eigenvalue is alpha / (2 pi).
    """
    cos_alpha = max(-1.0, min(1.0, (matrix[0][0] + matrix[1][1]) / 2.0))
    return math.acos(cos_alpha) / (2.0 * math.pi)


def rotation_eigenvector():
    """Eigenvector of rotation_unitary for eigenvalue exp(+i alpha)."""
    return [1.0 / _SQRT2, -1j / _SQRT2]


def qpe_distribution(t, unitary, target):
    """Run QPE and return exact outcome probabilities over 2^t cells.

    target is the target qubit's initial 2-amplitude state. The
    probabilities are read off the final statevector - this is the
    full distribution, not a sample from it.
    """
    size = 1 << (t + 1)
    state = [0j] * size
    state[0] = target[0]
    state[1 << t] = target[1]
    for k in range(t):
        apply_single(state, k, H_GATE)
    for k in range(t):
        apply_controlled(state, k, t, mat_pow2(unitary, k))
    apply_qft(state, t, inverse=True)
    mask = (1 << t) - 1
    probs = [0.0] * (1 << t)
    for i, amp in enumerate(state):
        probs[i & mask] += abs(amp) ** 2
    return probs


def peak_of(probs):
    """(index, probability) of the most likely outcome."""
    y = max(range(len(probs)), key=lambda i: probs[i])
    return y, probs[y]


def delta_cells(theta, t):
    """Distance from theta to the nearest 2^t grid point, in cells.

    0.0 means theta is exactly representable at t bits; 0.5 is the
    worst case, exactly halfway between two grid points.
    """
    m = theta * (1 << t)
    return abs(m - round(m))


def dirichlet_peak(t, delta):
    """Peak probability from the Dirichlet kernel.

    delta is the signed distance (in turns) from theta to the peak
    grid point. P = (1/2^(2t)) * sin^2(2^t pi delta) / sin^2(pi delta).
    """
    n = 1 << t
    if abs(delta) < 1e-15:
        return 1.0
    return (math.sin(math.pi * n * delta) ** 2) / \
        (n * n * math.sin(math.pi * delta) ** 2)


def within_one_cell(t, theta):
    """P(measured cell within 1 cell of theta * 2^t), from the sim."""
    probs = qpe_distribution(t, phase_unitary(theta), [0.0, 1.0])
    n = 1 << t
    m = theta * n
    total = 0.0
    for y in range(n):
        d = min(abs(y - m), n - abs(y - m))
        if d <= 1.0 + 1e-12:
            total += probs[y]
    return total


# ================================================================ 3. Topic reports
def exact_report():
    """Theta exactly on the grid: the distribution is a delta."""
    t = 5
    theta = THETA_EXACT_NUM / (1 << t)
    probs = qpe_distribution(t, phase_unitary(theta), [0.0, 1.0])
    y, p = peak_of(probs)
    return {
        "theta": theta,
        "t": t,
        "peak_outcome": y,
        "peak_probability": round(p, 12),
        "probability_elsewhere": round(sum(probs) - p, 12),
        "why": "theta = j/2^t makes every controlled phase a whole "
               "number of turns on the grid, so the inverse QFT "
               "interferes constructively on exactly one outcome",
    }


def kernel_report():
    """Off-grid phases: simulator graded against the Dirichlet kernel."""
    rows = []
    for t, theta in ((4, 0.31), (5, THETA_SWEEP), (6, 0.707),
                     (7, 0.1234), (8, THETA_SWEEP)):
        probs = qpe_distribution(t, phase_unitary(theta), [0.0, 1.0])
        y, p = peak_of(probs)
        delta = theta - y / (1 << t)
        formula = dirichlet_peak(t, delta)
        rows.append({
            "t": t, "theta": theta, "peak_outcome": y,
            "delta_cells": round(delta_cells(theta, t), 6),
            "p_simulator": round(p, 9),
            "p_dirichlet": round(formula, 9),
            "abs_diff": float(f"{abs(p - formula):.3e}"),
        })
    within = []
    for t in range(3, 9):
        within.append({"t": t, "theta": THETA_SWEEP,
                       "p_within_1_cell": round(within_one_cell(t, THETA_SWEEP), 6)})
    return {"graded_peaks": rows, "within_one_cell_theta_0.3": within}


def ledger_report():
    """The precision ledger: accuracy bought vs controlled-U cost."""
    rows = []
    for t in range(3, 9):
        rows.append({
            "t": t,
            "grid_spacing": 2.0 ** (-t),
            "controlled_u_applications": (1 << t) - 1,
            "inverse_qft_controlled_phases": t * (t - 1) // 2,
            "simulator_amplitudes": 1 << (t + 1),
        })
    return {"rows": rows,
            "rule": "each extra counting qubit halves the grid "
                    "spacing and roughly doubles the controlled-U "
                    "bill (2^t - 1 applications at t bits)"}


def energy_report():
    """Toy application: rotation eigenphase -> labelled 'energy'.

    E = -2 pi theta / tau with tau labelled. The unitary is a toy
    Hamiltonian stand-in, not a molecule; the table shows the
    estimate and its error bar shrinking with t.
    """
    unitary = rotation_unitary(ROTATION_ALPHA)
    theta_true = eigenphase_from_trace(unitary)
    e_true = -2.0 * math.pi * theta_true / TAU
    rows = []
    for t in range(3, 9):
        probs = qpe_distribution(t, unitary, rotation_eigenvector())
        y, p = peak_of(probs)
        theta_est = y / (1 << t)
        e_est = -2.0 * math.pi * theta_est / TAU
        rows.append({
            "t": t, "peak_outcome": y, "peak_probability": round(p, 6),
            "theta_estimate": round(theta_est, 6),
            "energy_estimate": round(e_est, 6),
            "abs_error": round(abs(e_est - e_true), 6),
            "grid_error_bound": round(2.0 * math.pi / (TAU * (1 << t)), 6),
        })
    return {
        "unitary": "rotation by alpha = 0.7 rad (labelled toy)",
        "tau": TAU,
        "theta_true_from_trace": round(theta_true, 9),
        "energy_true": round(e_true, 6),
        "conversion": "E = -2*pi*theta/tau (labelled scale, not chemistry)",
        "rows": rows,
    }


def superposition_report():
    """Non-eigenstate inputs: both eigenphases appear, Born-weighted.

    Leakage is printed, not hidden: the mass outside the two peak
    neighbourhoods is part of the report.
    """
    t = 6
    # Phase unitary, input |+>: eigenphases 0 and 0.3, weights 1/2 each.
    probs = qpe_distribution(t, phase_unitary(THETA_SWEEP),
                             [1.0 / _SQRT2, 1.0 / _SQRT2])
    y_top, p_top = peak_of(probs)
    y_theta = round(THETA_SWEEP * (1 << t))
    near = sum(probs[y] for y in range(1 << t)
               if min(abs(y - 0), abs(y - y_theta)) <= 1)
    # Rotation, input |0>: equal superposition of the two eigenvectors.
    unitary = rotation_unitary(ROTATION_ALPHA)
    theta_r = eigenphase_from_trace(unitary)
    probs_r = qpe_distribution(t, unitary, [1.0, 0.0])
    top_r = sorted(range(1 << t), key=lambda i: -probs_r[i])[:2]
    return {
        "phase_unitary_input_plus": {
            "t": t, "theta": THETA_SWEEP,
            "peak_at_zero": {"outcome": y_top, "probability": round(p_top, 6)},
            "peak_at_theta": {"outcome": y_theta,
                              "probability": round(probs[y_theta], 6)},
            "mass_within_1_cell_of_either_peak": round(near, 6),
            "reading": "two eigenphases, Born weights 1/2 and 1/2, "
                       "each wearing its own Dirichlet peak shape",
        },
        "rotation_input_zero": {
            "t": t, "theta_from_trace": round(theta_r, 6),
            "top_two_outcomes": [
                {"outcome": y, "probability": round(probs_r[y], 6)}
                for y in sorted(top_r)],
            "reading": "|0> is an equal superposition of the two "
                       "rotation eigenvectors, so QPE returns theta "
                       "and 1 - theta with equal weight",
        },
    }


# ================================================================ 4. kNN run classifier
# Features: counting qubits t, distance-to-grid in cells, peak
# probability. The training grid is labelled by the lab's own policy
# (policy_label below) - the classifier interpolates the policy, it
# does not replace the exact distribution the simulator computed.

def policy_label(t, delta_cell, peak_p):
    """The lab's verdict policy distilled to a four-way label."""
    if delta_cell < 1e-9:
        return "exact"
    if peak_p < 0.35:
        return "leaky"
    if t <= 4:
        return "under-resolved"
    return "confident"


def _training_grid():
    rows = []
    for t in range(2, 9):
        for di in range(0, 11):
            d = di * 0.05
            for pi in range(0, 15):
                p = 0.16 + 0.06 * pi
                rows.append(((t, d, p), policy_label(t, d, p)))
    return rows


TRAINING_GRID = _training_grid()


def _scaled(features):
    t, d, p = features
    return (t / 8.0, d / 0.5, p)


def classify_run(t, delta_cell, peak_p, k=5):
    """kNN over the policy-labelled grid, deterministic tie-breaking."""
    target = _scaled((t, delta_cell, peak_p))
    ranked = []
    for features, label in TRAINING_GRID:
        point = _scaled(features)
        dist2 = sum((a - b) ** 2 for a, b in zip(target, point))
        ranked.append((dist2, features, label))
    ranked.sort(key=lambda row: (row[0], row[1]))
    votes = {}
    for _, _, label in ranked[:k]:
        votes[label] = votes.get(label, 0) + 1
    priority = {"exact": 0, "confident": 1, "leaky": 2, "under-resolved": 3}
    return sorted(votes.items(), key=lambda kv: (-kv[1], priority[kv[0]]))[0][0]


def _run_features(t, unitary, target, theta):
    probs = qpe_distribution(t, unitary, target)
    _, p = peak_of(probs)
    return (t, delta_cells(theta, t), p)


def classifier_report():
    """Scenarios whose features are measured from real simulator runs."""
    scenarios = {}
    t, d, p = _run_features(5, phase_unitary(13 / 32), [0.0, 1.0], 13 / 32)
    scenarios["exact_phase_t5"] = {
        "t": t, "delta_cells": round(d, 6), "peak_probability": round(p, 6),
        "verdict": classify_run(t, d, p)}
    t, d, p = _run_features(6, phase_unitary(THETA_SWEEP), [0.0, 1.0],
                            THETA_SWEEP)
    scenarios["off_grid_theta_0.3_t6"] = {
        "t": t, "delta_cells": round(d, 6), "peak_probability": round(p, 6),
        "verdict": classify_run(t, d, p)}
    t, d, p = _run_features(3, phase_unitary(THETA_SWEEP), [0.0, 1.0],
                            THETA_SWEEP)
    scenarios["off_grid_theta_0.3_t3"] = {
        "t": t, "delta_cells": round(d, 6), "peak_probability": round(p, 6),
        "verdict": classify_run(t, d, p)}
    # Leaky: |0> input to a rotation whose eigenphase sits exactly
    # half a cell off the t=6 grid - the mass splits four ways.
    alpha_leak = 2.0 * math.pi * (11.5 / 64)
    leak_unitary = rotation_unitary(alpha_leak)
    theta_leak = eigenphase_from_trace(leak_unitary)
    t, d, p = _run_features(6, leak_unitary, [1.0, 0.0], theta_leak)
    scenarios["superposition_half_cell_t6"] = {
        "t": t, "delta_cells": round(d, 6), "peak_probability": round(p, 6),
        "verdict": classify_run(t, d, p)}
    return scenarios


# ================================================================ 5. Advisory seats
def _trace(payload):
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True).encode()).hexdigest()[:16]


def argon4_decide(topic="quantumphaseestimation-demo"):
    """Gemini Argon 4 DECIDER seat: MAP->MODEL->STRESS->DECIDE.

    Names-only keys, live calls 0, tighten-only: can add HOLDs, never lift one.
    """
    stages = ["MAP", "MODEL", "STRESS", "DECIDE"]
    payload = {"seat": "gemini-argon-4", "topic": topic, "stages": stages}
    return {
        "seat": "Gemini Argon 4 Extended Thinking",
        "model_id": "gemini-argon-4",
        "role": "DECIDER",
        "pipeline": stages,
        "tiers": [2048, 8192, 32768],
        "key": "names-only (GEMINI_API_KEY name checked, value never read)",
        "live_calls": 0,
        "decision": "PROCEED - sandbox simulation only, all chemistry / hardware / speedup gates stay HOLD",
        "can_override_hold": False,
        "trace_sha256_16": _trace(payload),
    }


def claude_advisor(topic="quantumphaseestimation-demo"):
    """Muse advisor seat: advises, can never override a HOLD."""
    return {
        "seat": "Muse",
        "role": "ADVISOR",
        "key": "names-only (MODEL_API_KEY name checked, value never read)",
        "live_calls": 0,
        "advice": "Print the cost next to every accuracy claim: t bits of phase cost 2^t - 1 controlled-U applications, and the simulator itself pays 2^n amplitudes - say both, every time.",
        "can_override_hold": False,
    }


def google_flow_plan():
    """Google Flow seat: plan-only, nothing rendered, nothing live."""
    return {
        "seat": "Google Flow",
        "role": "PLAN-ONLY",
        "shots": ["a counting register fanning into controlled powers of U",
                  "phase kickback writing theta across the counting qubits",
                  "the inverse QFT combing a spread distribution into one peak",
                  "an off-grid phase leaking into neighbouring cells",
                  "a precision ledger balancing bits against controlled-U cost"],
        "rendered": False,
        "live": 0,
    }


def brains_report():
    return {"decider": argon4_decide(), "advisor": claude_advisor(),
            "flow": google_flow_plan()}


# ================================================================ checks
def run_checks():
    c = []

    def chk(name, ok):
        c.append((name, bool(ok)))

    # 1. simulator + QFT graded against the direct DFT definition
    for inverse, sign in ((False, 1.0), (True, -1.0)):
        t = 3
        n = 1 << t
        worst = 0.0
        for x in range(n):
            state = [0j] * n
            state[x] = 1.0
            apply_qft(state, t, inverse=inverse)
            for y in range(n):
                want = cmath.exp(sign * 2j * math.pi * x * y / n) / math.sqrt(n)
                worst = max(worst, abs(state[y] - want))
        chk(f"qft_{'inverse' if inverse else 'forward'}_matches_dft",
            worst < 1e-12)
    state = [0j] * 16
    state[3] = 1.0
    apply_qft(state, 4, inverse=False)
    apply_qft(state, 4, inverse=True)
    chk("qft_inverse_undoes_forward", abs(state[3] - 1.0) < 1e-12
        and abs(sum(abs(a) ** 2 for a in state) - 1.0) < 1e-12)
    rot = rotation_unitary(0.7)
    chk("mat_pow2_matches_repeated_multiply",
        all(abs(mat_pow2(rot, 3)[i][j]
                - mat_mul(mat_mul(mat_mul(rot, rot), mat_mul(rot, rot)),
                          mat_mul(mat_mul(rot, rot), mat_mul(rot, rot)))[i][j])
            < 1e-12 for i in range(2) for j in range(2)))
    chk("phase_unitary_eigenstate",
        abs(phase_unitary(0.3)[1][1] - cmath.exp(2j * math.pi * 0.3)) < 1e-15)
    theta_rot = eigenphase_from_trace(rot)
    chk("rotation_eigenphase_from_trace",
        abs(theta_rot - 0.7 / (2.0 * math.pi)) < 1e-12)
    v = rotation_eigenvector()
    lam = cmath.exp(1j * 0.7)
    chk("rotation_eigenvector_eigenequation",
        abs(rot[0][0] * v[0] + rot[0][1] * v[1] - lam * v[0]) < 1e-12
        and abs(rot[1][0] * v[0] + rot[1][1] * v[1] - lam * v[1]) < 1e-12)

    # 2. exact phases: delta distributions
    probs = qpe_distribution(5, phase_unitary(13 / 32), [0.0, 1.0])
    chk("exact_phase_delta_t5", probs[13] > 1.0 - 1e-12
        and sum(probs) - probs[13] < 1e-12)
    probs = qpe_distribution(4, phase_unitary(6 / 16), [0.0, 1.0])
    chk("exact_phase_delta_t4", probs[6] > 1.0 - 1e-12)
    probs = qpe_distribution(4, phase_unitary(0.0), [0.0, 1.0])
    chk("exact_phase_zero", probs[0] > 1.0 - 1e-12)
    chk("distribution_normalised",
        all(abs(sum(qpe_distribution(t, phase_unitary(0.3), [0.0, 1.0])) - 1.0)
            < 1e-9 for t in (3, 5, 8)))

    # 3. Dirichlet kernel agreement at several (t, delta)
    for t, theta in ((4, 0.31), (5, 0.3), (6, 0.707), (7, 0.1234), (8, 0.3)):
        probs = qpe_distribution(t, phase_unitary(theta), [0.0, 1.0])
        y, p = peak_of(probs)
        formula = dirichlet_peak(t, theta - y / (1 << t))
        chk(f"dirichlet_agreement_t{t}", abs(p - formula) < 1e-9)
    # worst case: theta exactly half a cell off-grid, peak >= 4/pi^2 - eps
    theta_worst = 100.5 / 256
    probs = qpe_distribution(8, phase_unitary(theta_worst), [0.0, 1.0])
    _, p_worst = peak_of(probs)
    chk("dirichlet_worst_case_floor", p_worst >= 4.0 / math.pi ** 2 - 0.01)
    chk("delta_cells_range",
        all(0.0 <= delta_cells(th, 6) <= 0.5 + 1e-12
            for th in (0.0, 0.13, 0.3, 0.5, 0.77, 0.999)))
    probs5 = qpe_distribution(5, phase_unitary(0.3), [0.0, 1.0])
    m = 0.3 * 32
    within_sim = sum(probs5[y] for y in range(32)
                     if min(abs(y - m), 32 - abs(y - m)) <= 1.0 + 1e-12)
    chk("within_one_cell_matches_report",
        abs(within_sim - within_one_cell(5, 0.3)) < 1e-12)

    # 4. precision ledger arithmetic
    ledger = {row["t"]: row for row in ledger_report()["rows"]}
    chk("ledger_controlled_u_count",
        all(ledger[t]["controlled_u_applications"] == (1 << t) - 1
            for t in range(3, 9)))
    chk("ledger_iqft_phase_count",
        all(ledger[t]["inverse_qft_controlled_phases"] == t * (t - 1) // 2
            for t in range(3, 9)))
    chk("ledger_grid_spacing_halves",
        all(abs(ledger[t + 1]["grid_spacing"] - ledger[t]["grid_spacing"] / 2)
            < 1e-15 for t in range(3, 8)))
    chk("ledger_amplitudes_double",
        all(ledger[t + 1]["simulator_amplitudes"]
            == 2 * ledger[t]["simulator_amplitudes"] for t in range(3, 8)))

    # 5. energy toy: errors inside the grid bound, shrinking overall
    energy = energy_report()
    chk("energy_true_value", abs(energy["energy_true"] - (-1.4)) < 1e-6)
    chk("energy_errors_within_grid_bound",
        all(row["abs_error"] <= row["grid_error_bound"] + 1e-9
            for row in energy["rows"]))
    chk("energy_error_shrinks_t3_to_t8",
        energy["rows"][-1]["abs_error"] < energy["rows"][0]["abs_error"])
    chk("energy_theta_recovery",
        abs(energy["theta_true_from_trace"] - 0.7 / (2.0 * math.pi)) < 1e-9)

    # 6. superposition honesty: Born weights and printed leakage
    sup = superposition_report()
    plus = sup["phase_unitary_input_plus"]
    chk("superposition_peak_at_zero",
        plus["peak_at_zero"]["outcome"] == 0
        and 0.49 < plus["peak_at_zero"]["probability"] < 0.51)
    chk("superposition_theta_peak_born_weight",
        abs(plus["peak_at_theta"]["probability"]
            - 0.5 * dirichlet_peak(6, 0.3 - 19 / 64)) < 1e-6)
    rot_top = sup["rotation_input_zero"]["top_two_outcomes"]
    chk("superposition_rotation_two_equal_peaks",
        len(rot_top) == 2
        and abs(rot_top[0]["probability"] - rot_top[1]["probability"]) < 1e-9
        and all(0.47 < row["probability"] < 0.48 for row in rot_top))
    alpha_leak = 2.0 * math.pi * (11.5 / 64)
    probs_leak = qpe_distribution(6, rotation_unitary(alpha_leak), [1.0, 0.0])
    _, p_leak = peak_of(probs_leak)
    chk("superposition_half_cell_peak_spread", 0.15 < p_leak < 0.35)

    # 7. classifier - scenarios from real runs + full grid agreement
    rep = classifier_report()
    chk("classifier_exact_scenario",
        rep["exact_phase_t5"]["verdict"] == "exact")
    chk("classifier_confident_scenario",
        rep["off_grid_theta_0.3_t6"]["verdict"] == "confident")
    chk("classifier_under_resolved_scenario",
        rep["off_grid_theta_0.3_t3"]["verdict"] == "under-resolved")
    chk("classifier_leaky_scenario",
        rep["superposition_half_cell_t6"]["verdict"] == "leaky")
    chk("classifier_matches_policy_grid",
        all(classify_run(*features) == label
            for features, label in TRAINING_GRID))

    # 8. determinism: identical rerun of a full distribution
    chk("qpe_run_deterministic",
        qpe_distribution(6, phase_unitary(0.3), [0.0, 1.0])
        == qpe_distribution(6, phase_unitary(0.3), [0.0, 1.0]))

    # gates + seats
    chk("hold_gates_14", len(HOLD_GATES) == 14
        and all(v.startswith("HOLD") for v in HOLD_GATES.values()))
    chk("gate_chemistry_hold", gate("molecular_energy_claim") == "HOLD")
    chk("gate_hardware_hold", gate("quantum_hardware_run_claim") == "HOLD")
    chk("gate_speedup_hold", gate("quantum_speedup_claim") == "HOLD")
    chk("gate_crypto_hold", gate("cryptographic_use") == "HOLD")
    chk("gate_sandbox_proceed", gate("run_simulation") == "PROCEED")
    brains = brains_report()
    chk("argon4_no_override", brains["decider"]["can_override_hold"] is False
        and brains["decider"]["seat"] == "Gemini Argon 4 Extended Thinking"
        and brains["decider"]["model_id"] == "gemini-argon-4")
    chk("claude_no_override", brains["advisor"]["can_override_hold"] is False)
    chk("flow_plan_only", brains["flow"]["rendered"] is False
        and brains["flow"]["live"] == 0)
    return c


# ================================================================ CLI / demo
def demo():
    print("=" * 68)
    print("QuantumPhaseEstimation-Lab - quantum phase estimation lab")
    print("by Darion Kellar | MIT | pure stdlib | zero network | EDUCATION ONLY")
    print("=" * 68)
    print("\n[1] THE HONEST CORE - what QPE does and does not do")
    print("    QPE reads the eigenphase theta of a unitary U out of the")
    print("    phase kickback on a counting register, sharpened by an")
    print("    inverse QFT. This lab runs the real circuit on a classical")
    print("    statevector simulator and reads the EXACT outcome")
    print("    distribution off the state - no sampling.")
    print("    It computed no molecule's energy and ran on no quantum")
    print("    hardware. The simulator pays 2^n amplitudes; every")
    print("    accuracy figure below is printed next to its cost.")
    exact = exact_report()
    print("\n[2] Exact phases - when theta sits on the grid")
    print(f"    theta = 13/32 at t = 5: outcome {exact['peak_outcome']} "
          f"with probability {exact['peak_probability']:.6f}, "
          f"elsewhere {exact['probability_elsewhere']:.6f}")
    print("    -> a whole number of turns per controlled power makes")
    print("       the inverse QFT interfere onto exactly one cell.")
    kernel = kernel_report()
    print("\n[3] Off-grid phases - graded against the Dirichlet kernel")
    for row in kernel["graded_peaks"]:
        print(f"    t={row['t']} theta={row['theta']:<7} peak "
              f"{row['p_simulator']:.6f} vs formula {row['p_dirichlet']:.6f} "
              f"(diff {row['abs_diff']:.1e})")
    print("    P(within 1 cell of theta = 0.3):")
    for row in kernel["within_one_cell_theta_0.3"]:
        print(f"    t={row['t']}: {row['p_within_1_cell']:.6f}")
    print("    -> the within-1-cell mass oscillates with the fractional")
    print("       offset; what shrinks monotonically is the cell size.")
    print("\n[4] Precision ledger - accuracy is bought, not free")
    for row in ledger_report()["rows"]:
        print(f"    t={row['t']}: grid {row['grid_spacing']:.6f} | "
              f"controlled-U x{row['controlled_u_applications']:<4} | "
              f"inverse-QFT phases {row['inverse_qft_controlled_phases']:<3} | "
              f"simulator amplitudes {row['simulator_amplitudes']}")
    energy = energy_report()
    print("\n[5] Toy application - rotation eigenphase as a labelled 'energy'")
    print(f"    E = -2*pi*theta/tau, tau = {energy['tau']} | "
          f"true theta {energy['theta_true_from_trace']:.6f} | "
          f"true E {energy['energy_true']:.6f}")
    for row in energy["rows"]:
        print(f"    t={row['t']}: E_est {row['energy_estimate']:+.6f} | "
              f"error {row['abs_error']:.6f} | "
              f"grid bound {row['grid_error_bound']:.6f}")
    print("    -> a labelled toy Hamiltonian stand-in, not chemistry.")
    sup = superposition_report()
    print("\n[6] Non-eigenstate inputs - both peaks, leakage printed")
    plus = sup["phase_unitary_input_plus"]
    print(f"    |+> into phase unitary (theta = 0.3): peak at 0 is "
          f"{plus['peak_at_zero']['probability']:.6f}, peak at theta is "
          f"{plus['peak_at_theta']['probability']:.6f}, mass within "
          f"1 cell of either: {plus['mass_within_1_cell_of_either_peak']:.6f}")
    rot0 = sup["rotation_input_zero"]
    tops = ", ".join(f"outcome {r['outcome']} at {r['probability']:.6f}"
                     for r in rot0["top_two_outcomes"])
    print(f"    |0> into rotation: {tops}")
    print("    -> a superposition input returns both eigenphases with")
    print("       their Born weights. QPE does not pick a favourite.")
    print("\n[7] Run classifier (TinyML kNN, labels from the lab's policy)")
    for name, row in classifier_report().items():
        print(f"    {name:28s} t={row['t']} delta {row['delta_cells']:.3f} "
              f"peak {row['peak_probability']:.6f} -> {row['verdict']}")
    print("\n[8] Advisory seats")
    brains = brains_report()
    print(f"    decider: {brains['decider']['decision']} "
          f"trace={brains['decider']['trace_sha256_16']}")
    print(f"    advisor can_override_hold = {brains['advisor']['can_override_hold']}")
    print(f"    flow rendered = {brains['flow']['rendered']} "
          f"live = {brains['flow']['live']}")
    print(f"\n[9] HOLD gates: {len(HOLD_GATES)}")
    for key in HOLD_GATES:
        print(f"    HOLD  {key}")
    checks = run_checks()
    passed = sum(1 for _, ok in checks if ok)
    print(f"\nCHECKS {passed}/{len(checks)}")
    for name, ok in checks:
        if not ok:
            print(f"    FAIL {name}")
    verdict = "PROCEED" if passed == len(checks) else "HOLD"
    print(f"VERDICT {verdict} (sandbox simulation only) | HOLD gates {len(HOLD_GATES)}")
    return 0 if passed == len(checks) else 1


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] == "demo":
        return demo()
    cmd = argv[0]
    if cmd == "checks":
        checks = run_checks()
        for name, ok in checks:
            print(f"{'PASS' if ok else 'FAIL'} {name}")
        print(f"CHECKS {sum(1 for _, ok in checks if ok)}/{len(checks)}")
        return 0 if all(ok for _, ok in checks) else 1
    if cmd == "exact":
        print(json.dumps(exact_report(), indent=2, sort_keys=True))
        return 0
    if cmd == "kernel":
        print(json.dumps(kernel_report(), indent=2, sort_keys=True))
        return 0
    if cmd == "ledger":
        print(json.dumps(ledger_report(), indent=2, sort_keys=True))
        return 0
    if cmd == "energy":
        print(json.dumps(energy_report(), indent=2, sort_keys=True))
        return 0
    if cmd == "superposition":
        print(json.dumps(superposition_report(), indent=2, sort_keys=True))
        return 0
    if cmd == "classify":
        print(json.dumps(classifier_report(), indent=2, sort_keys=True))
        return 0
    if cmd == "brains":
        print(json.dumps(brains_report(), indent=2, sort_keys=True))
        return 0
    if cmd == "holds":
        for key, value in HOLD_GATES.items():
            print(f"{key}: {value}")
        return 0
    if cmd == "hold-demo":
        action = argv[1] if len(argv) > 1 else "molecular_energy_claim"
        print(f"{action}: {HOLD_GATES.get(action, 'PROCEED - not gated')}")
        return 2 if gate(action) == "HOLD" else 0
    print(__doc__)
    return 0


if __name__ == "__main__":
    sys.exit(main())
