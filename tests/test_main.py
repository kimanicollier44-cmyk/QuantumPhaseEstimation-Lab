"""Tests for QuantumPhaseEstimation-Lab.

Every headline number in the README is asserted here against an
independent route: the QFT against the direct DFT definition, the
peak probabilities against the Dirichlet kernel, the energy errors
against the grid bound, and the classifier against the lab's own
policy on every grid row.
"""
import cmath
import math
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import main as lab


# ---------------------------------------------------------------- simulator
def test_qft_forward_matches_dft():
    t, n = 3, 8
    for x in range(n):
        state = [0j] * n
        state[x] = 1.0
        lab.apply_qft(state, t, inverse=False)
        for y in range(n):
            want = cmath.exp(2j * math.pi * x * y / n) / math.sqrt(n)
            assert abs(state[y] - want) < 1e-12


def test_qft_inverse_matches_dft():
    t, n = 3, 8
    for x in range(n):
        state = [0j] * n
        state[x] = 1.0
        lab.apply_qft(state, t, inverse=True)
        for y in range(n):
            want = cmath.exp(-2j * math.pi * x * y / n) / math.sqrt(n)
            assert abs(state[y] - want) < 1e-12


def test_qft_roundtrip():
    state = [0j] * 16
    state[5] = 1.0
    lab.apply_qft(state, 4, inverse=False)
    lab.apply_qft(state, 4, inverse=True)
    assert abs(state[5] - 1.0) < 1e-12


def test_mat_pow2_is_repeated_squaring():
    rot = lab.rotation_unitary(0.7)
    r2 = lab.mat_mul(rot, rot)
    r8 = lab.mat_mul(lab.mat_mul(r2, r2), lab.mat_mul(r2, r2))
    got = lab.mat_pow2(rot, 3)
    for i in range(2):
        for j in range(2):
            assert abs(got[i][j] - r8[i][j]) < 1e-12


def test_rotation_eigenphase_from_trace():
    theta = lab.eigenphase_from_trace(lab.rotation_unitary(0.7))
    assert abs(theta - 0.7 / (2 * math.pi)) < 1e-12


def test_rotation_eigenvector_satisfies_eigenequation():
    rot = lab.rotation_unitary(0.7)
    v = lab.rotation_eigenvector()
    lam = cmath.exp(1j * 0.7)
    assert abs(rot[0][0] * v[0] + rot[0][1] * v[1] - lam * v[0]) < 1e-12
    assert abs(rot[1][0] * v[0] + rot[1][1] * v[1] - lam * v[1]) < 1e-12


# ---------------------------------------------------------------- exact phases
def test_exact_phase_is_delta_t5():
    probs = lab.qpe_distribution(5, lab.phase_unitary(13 / 32), [0.0, 1.0])
    assert probs[13] > 1.0 - 1e-12
    assert sum(probs) - probs[13] < 1e-12


def test_exact_phase_is_delta_t4():
    probs = lab.qpe_distribution(4, lab.phase_unitary(6 / 16), [0.0, 1.0])
    assert probs[6] > 1.0 - 1e-12


def test_exact_phase_zero():
    probs = lab.qpe_distribution(4, lab.phase_unitary(0.0), [0.0, 1.0])
    assert probs[0] > 1.0 - 1e-12


def test_distribution_normalised():
    for t in (3, 5, 8):
        probs = lab.qpe_distribution(t, lab.phase_unitary(0.3), [0.0, 1.0])
        assert abs(sum(probs) - 1.0) < 1e-9


def test_exact_report():
    rep = lab.exact_report()
    assert rep["peak_outcome"] == 13
    assert rep["peak_probability"] > 1.0 - 1e-9
    assert rep["probability_elsewhere"] < 1e-9


# ---------------------------------------------------------------- Dirichlet kernel
def test_dirichlet_agreement_sweep():
    for t, theta in ((4, 0.31), (5, 0.3), (6, 0.707), (7, 0.1234), (8, 0.3)):
        probs = lab.qpe_distribution(t, lab.phase_unitary(theta), [0.0, 1.0])
        y, p = lab.peak_of(probs)
        formula = lab.dirichlet_peak(t, theta - y / (1 << t))
        assert abs(p - formula) < 1e-9


def test_dirichlet_worst_case_floor():
    probs = lab.qpe_distribution(8, lab.phase_unitary(100.5 / 256), [0.0, 1.0])
    _, p = lab.peak_of(probs)
    assert p >= 4.0 / math.pi ** 2 - 0.01


def test_delta_cells_bounds():
    for th in (0.0, 0.13, 0.3, 0.5, 0.77, 0.999):
        assert 0.0 <= lab.delta_cells(th, 6) <= 0.5 + 1e-12
    assert lab.delta_cells(13 / 32, 5) < 1e-12
    assert abs(lab.delta_cells(0.3, 6) - 0.2) < 1e-12


def test_within_one_cell_range():
    for t in range(3, 9):
        p = lab.within_one_cell(t, 0.3)
        assert 0.8 < p < 0.95


def test_kernel_report_rows():
    rep = lab.kernel_report()
    assert len(rep["graded_peaks"]) == 5
    assert all(row["abs_diff"] < 1e-9 for row in rep["graded_peaks"])
    assert len(rep["within_one_cell_theta_0.3"]) == 6


# ---------------------------------------------------------------- ledger
def test_ledger_counts():
    rows = {row["t"]: row for row in lab.ledger_report()["rows"]}
    for t in range(3, 9):
        assert rows[t]["controlled_u_applications"] == (1 << t) - 1
        assert rows[t]["inverse_qft_controlled_phases"] == t * (t - 1) // 2
        assert rows[t]["simulator_amplitudes"] == 1 << (t + 1)
        assert abs(rows[t]["grid_spacing"] - 2.0 ** (-t)) < 1e-15


# ---------------------------------------------------------------- energy toy
def test_energy_true_value():
    rep = lab.energy_report()
    assert abs(rep["energy_true"] - (-1.4)) < 1e-6
    assert abs(rep["theta_true_from_trace"] - 0.7 / (2 * math.pi)) < 1e-9


def test_energy_errors_within_grid_bound():
    rep = lab.energy_report()
    for row in rep["rows"]:
        assert row["abs_error"] <= row["grid_error_bound"] + 1e-9


def test_energy_error_shrinks_overall():
    rows = lab.energy_report()["rows"]
    assert rows[-1]["abs_error"] < rows[0]["abs_error"]


# ---------------------------------------------------------------- superposition
def test_superposition_plus_input_two_peaks():
    rep = lab.superposition_report()["phase_unitary_input_plus"]
    assert rep["peak_at_zero"]["outcome"] == 0
    assert 0.49 < rep["peak_at_zero"]["probability"] < 0.51
    want = 0.5 * lab.dirichlet_peak(6, 0.3 - 19 / 64)
    assert abs(rep["peak_at_theta"]["probability"] - want) < 1e-6
    assert rep["mass_within_1_cell_of_either_peak"] > 0.9


def test_superposition_rotation_input_zero():
    rep = lab.superposition_report()["rotation_input_zero"]
    top = rep["top_two_outcomes"]
    assert len(top) == 2
    assert abs(top[0]["probability"] - top[1]["probability"]) < 1e-9
    assert all(0.47 < row["probability"] < 0.48 for row in top)
    outcomes = {row["outcome"] for row in top}
    assert outcomes == {7, 57}


def test_superposition_half_cell_spreads_peak():
    alpha = 2.0 * math.pi * (11.5 / 64)
    probs = lab.qpe_distribution(6, lab.rotation_unitary(alpha), [1.0, 0.0])
    _, p = lab.peak_of(probs)
    assert 0.15 < p < 0.35


# ---------------------------------------------------------------- classifier
def test_classifier_scenarios():
    rep = lab.classifier_report()
    assert rep["exact_phase_t5"]["verdict"] == "exact"
    assert rep["off_grid_theta_0.3_t6"]["verdict"] == "confident"
    assert rep["off_grid_theta_0.3_t3"]["verdict"] == "under-resolved"
    assert rep["superposition_half_cell_t6"]["verdict"] == "leaky"


def test_classifier_matches_policy_on_grid():
    for features, label in lab.TRAINING_GRID:
        assert lab.classify_run(*features) == label


def test_policy_label_corners():
    assert lab.policy_label(5, 0.0, 1.0) == "exact"
    assert lab.policy_label(6, 0.2, 0.87) == "confident"
    assert lab.policy_label(3, 0.4, 0.58) == "under-resolved"
    assert lab.policy_label(6, 0.5, 0.20) == "leaky"


# ---------------------------------------------------------------- gates + seats
def test_hold_gates():
    assert len(lab.HOLD_GATES) == 14
    assert all(v.startswith("HOLD") for v in lab.HOLD_GATES.values())
    assert lab.gate("molecular_energy_claim") == "HOLD"
    assert lab.gate("quantum_hardware_run_claim") == "HOLD"
    assert lab.gate("quantum_speedup_claim") == "HOLD"
    assert lab.gate("cryptographic_use") == "HOLD"
    assert lab.gate("run_simulation") == "PROCEED"


def test_seats_never_override():
    brains = lab.brains_report()
    assert brains["decider"]["can_override_hold"] is False
    assert brains["decider"]["seat"] == "Gemini Argon 4 Extended Thinking"
    assert brains["decider"]["model_id"] == "gemini-argon-4"
    assert brains["decider"]["live_calls"] == 0
    assert brains["advisor"]["can_override_hold"] is False
    assert brains["flow"]["rendered"] is False
    assert brains["flow"]["live"] == 0


# ---------------------------------------------------------------- CLI + checks
def test_run_checks_all_pass():
    checks = lab.run_checks()
    assert all(ok for _, ok in checks), [n for n, ok in checks if not ok]
    assert len(checks) >= 40


def test_qpe_deterministic():
    a = lab.qpe_distribution(6, lab.phase_unitary(0.3), [0.0, 1.0])
    b = lab.qpe_distribution(6, lab.phase_unitary(0.3), [0.0, 1.0])
    assert a == b


def _run_cli(*args):
    return subprocess.run(
        [sys.executable, str(Path(__file__).resolve().parent.parent / "main.py"),
         *args], capture_output=True, text=True)


def test_cli_hold_demo_exits_2():
    proc = _run_cli("hold-demo")
    assert proc.returncode == 2
    assert "HOLD" in proc.stdout


def test_cli_checks_pass():
    proc = _run_cli("checks")
    assert proc.returncode == 0
    assert "CHECKS" in proc.stdout


def test_cli_demo_deterministic():
    a = _run_cli("demo")
    b = _run_cli("demo")
    assert a.returncode == 0 and b.returncode == 0
    assert a.stdout == b.stdout
