"""
DFTGuard — Memory BIST / JTAG / ATPG / IO BIST Engine
Simulates DFT coverage analysis, fault simulation, testplan generation
Maps to NVIDIA DFT Team JD: Memory BIST, JTAG, ATPG, UVM coverage metrics
"""
from __future__ import annotations
import random, math, uuid
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
from enum import Enum

# ─── Enums ────────────────────────────────────────────────────────────────────

class FaultType(str, Enum):
    STUCK_AT_0   = "Stuck-at-0"
    STUCK_AT_1   = "Stuck-at-1"
    TRANSITION   = "Transition"
    BRIDGING     = "Bridging"
    IDDQ         = "IDDQ"
    CELL_AWARE   = "Cell-aware"

class BISTAlgorithm(str, Enum):
    MARCH_C    = "March-C"
    MARCH_CM   = "March-CM"
    MATS_PLUS  = "MATS+"
    GALPAT     = "GALPAT"
    WALKING_1  = "Walking-1s"
    MARCH_LR   = "March-LR"

class TestMode(str, Enum):
    FUNCTIONAL   = "Functional"
    SCAN         = "Scan"
    BIST         = "BIST"
    MBIST        = "Memory-BIST"
    JTAG         = "JTAG"
    IO_BIST      = "IO-BIST"

# ─── Data Models ──────────────────────────────────────────────────────────────

@dataclass
class MemorySpec:
    name: str = "SRAM_512x32"
    depth: int = 512        # number of words
    width: int = 32         # bits per word
    num_ports: int = 1
    has_ecc: bool = True
    ecc_bits: int = 7       # SECDED for 32-bit word

    @property
    def total_bits(self) -> int:
        return self.depth * (self.width + self.ecc_bits if self.has_ecc else self.width)

    @property
    def march_c_ops(self) -> int:
        # March-C: 6 passes × depth × width operations
        return 6 * self.depth * self.width

@dataclass
class BISTResult:
    memory_name: str
    algorithm: BISTAlgorithm
    total_cells: int
    faults_detected: int
    faults_total: int
    coverage_pct: float
    ecc_corrections: int
    uncorrectable_errors: int
    test_time_ns: float
    pass_fail: str
    fault_breakdown: Dict[str, int]

@dataclass
class JTAGChain:
    chain_id: str
    tap_count: int = 4
    ir_length: int = 5
    instructions: List[str] = field(default_factory=lambda: [
        "BYPASS", "EXTEST", "SAMPLE/PRELOAD", "IDCODE",
        "INTEST", "CLAMP", "HIGHZ", "RUNBIST"
    ])
    bsr_length: int = 256   # boundary scan register length

@dataclass
class JTAGResult:
    chain_id: str
    connectivity_pass: bool
    ir_capture_ok: bool
    dr_capture_ok: bool
    bsr_tested_cells: int
    bsr_faults: int
    idcode_correct: bool
    coverage_pct: float

@dataclass
class ScanChain:
    chain_id: str
    length: int             # number of scan FFs
    clock_domain: str
    test_mode: str

@dataclass
class ATPGResult:
    fault_type: FaultType
    total_faults: int
    detected_faults: int
    atpg_detected: int
    simulation_detected: int
    redundant_faults: int
    undetected_faults: int
    coverage_pct: float
    pattern_count: int
    test_time_ms: float
    compression_ratio: float

@dataclass
class DFTCoverage:
    """Full DFT coverage report — maps to NVIDIA DFT team requirements"""
    design_name: str
    technology: str
    total_flops: int
    scan_flops: int
    scan_coverage_pct: float
    mbist_memories: List[BISTResult]
    jtag_results: List[JTAGResult]
    atpg_results: List[ATPGResult]
    overall_fault_coverage: float
    stuck_at_coverage: float
    transition_coverage: float
    cell_aware_coverage: float
    observations: List[str]
    recommendations: List[str]

# ─── BIST Engine ──────────────────────────────────────────────────────────────

class MemoryBISTEngine:
    """Simulates Memory BIST execution — March algorithms, ECC verification"""

    ALGORITHM_COVERAGE = {
        BISTAlgorithm.MARCH_C:   {"SA": 0.997, "TF": 0.961, "CF":  0.890, "NPSF": 0.720},
        BISTAlgorithm.MARCH_CM:  {"SA": 0.998, "TF": 0.975, "CF":  0.932, "NPSF": 0.841},
        BISTAlgorithm.MATS_PLUS: {"SA": 0.985, "TF": 0.812, "CF":  0.0,   "NPSF": 0.0},
        BISTAlgorithm.GALPAT:    {"SA": 0.999, "TF": 0.996, "CF":  0.998, "NPSF": 0.960},
        BISTAlgorithm.WALKING_1: {"SA": 0.999, "TF": 0.994, "CF":  0.996, "NPSF": 0.950},
        BISTAlgorithm.MARCH_LR:  {"SA": 0.998, "TF": 0.988, "CF":  0.961, "NPSF": 0.880},
    }

    def run(self, mem: MemorySpec, algo: BISTAlgorithm, seed: int = 42) -> BISTResult:
        rng = random.Random(seed + hash(mem.name) % 1000)
        cov = self.ALGORITHM_COVERAGE[algo]

        total_cells = mem.total_bits
        # Fault universe: stuck-at faults (2 per cell) + transition + coupling
        sa_faults    = total_cells * 2
        tf_faults    = total_cells * 2
        cf_faults    = int(total_cells * 0.3)
        total_faults = sa_faults + tf_faults + cf_faults

        # Detected faults
        sa_det  = int(sa_faults * cov["SA"]  * (1 + rng.gauss(0, 0.002)))
        tf_det  = int(tf_faults * cov["TF"]  * (1 + rng.gauss(0, 0.004)))
        cf_det  = int(cf_faults * cov["CF"]  * (1 + rng.gauss(0, 0.008)))
        detected = min(sa_det + tf_det + cf_det, total_faults)

        # ECC
        ecc_corrections      = rng.randint(0, 2) if mem.has_ecc else 0
        uncorrectable_errors = rng.randint(0, 1) if not mem.has_ecc else 0

        # Test time: March-C is O(n), GALPAT is O(n²)
        base_time_per_bit_ns = 2.5
        if algo in [BISTAlgorithm.GALPAT, BISTAlgorithm.WALKING_1]:
            test_time = base_time_per_bit_ns * total_cells * math.sqrt(total_cells) / 1000
        else:
            test_time = base_time_per_bit_ns * mem.march_c_ops / 1e3

        coverage = detected / total_faults * 100
        return BISTResult(
            memory_name=mem.name, algorithm=algo,
            total_cells=total_cells,
            faults_detected=detected, faults_total=total_faults,
            coverage_pct=round(coverage, 2),
            ecc_corrections=ecc_corrections,
            uncorrectable_errors=uncorrectable_errors,
            test_time_ns=round(test_time, 1),
            pass_fail="PASS" if coverage >= 99.0 and uncorrectable_errors == 0 else "FAIL",
            fault_breakdown={"stuck_at": sa_det, "transition": tf_det, "coupling": cf_det}
        )

# ─── JTAG Engine ──────────────────────────────────────────────────────────────

class JTAGEngine:
    """Simulates JTAG BScan connectivity and IDCODE verification"""

    def run(self, chain: JTAGChain, seed: int = 99) -> JTAGResult:
        rng = random.Random(seed)
        bsr_cells   = chain.bsr_length
        bsr_faults  = rng.randint(0, 2)
        cov         = (bsr_cells - bsr_faults) / bsr_cells * 100

        return JTAGResult(
            chain_id=chain.chain_id,
            connectivity_pass=True,
            ir_capture_ok=True,
            dr_capture_ok=True,
            bsr_tested_cells=bsr_cells,
            bsr_faults=bsr_faults,
            idcode_correct=True,
            coverage_pct=round(cov, 2),
        )

# ─── ATPG Engine ──────────────────────────────────────────────────────────────

class ATPGEngine:
    """Simulates ATPG pattern generation — Stuck-at, Transition, Cell-aware"""

    BASE_COVERAGE = {
        FaultType.STUCK_AT_0:  (0.991, 0.997),
        FaultType.STUCK_AT_1:  (0.990, 0.996),
        FaultType.TRANSITION:  (0.971, 0.985),
        FaultType.BRIDGING:    (0.880, 0.925),
        FaultType.CELL_AWARE:  (0.952, 0.972),
        FaultType.IDDQ:        (0.840, 0.890),
    }

    def run(self, total_gates: int, fault_type: FaultType,
            scan_coverage_pct: float, seed: int = 7) -> ATPGResult:
        rng = random.Random(seed + hash(fault_type) % 100)
        lo, hi = self.BASE_COVERAGE[fault_type]

        # Scale coverage by scan insertion rate
        scan_scale = scan_coverage_pct / 100.0
        base_cov   = rng.uniform(lo, hi) * scan_scale

        total_faults     = total_gates * 2
        detected         = int(total_faults * base_cov)
        redundant        = int(total_faults * rng.uniform(0.008, 0.018))
        undetected       = total_faults - detected - redundant
        atpg_det         = int(detected * 0.88)
        sim_det          = detected - atpg_det

        patterns         = int(total_gates / rng.uniform(18, 28))
        compression      = rng.uniform(8, 20)
        test_time_ms     = patterns * rng.uniform(0.15, 0.35)

        coverage_pct = detected / (total_faults - redundant) * 100 if total_faults > redundant else 0

        return ATPGResult(
            fault_type=fault_type,
            total_faults=total_faults,
            detected_faults=detected,
            atpg_detected=atpg_det,
            simulation_detected=sim_det,
            redundant_faults=redundant,
            undetected_faults=undetected,
            coverage_pct=round(coverage_pct, 2),
            pattern_count=patterns,
            test_time_ms=round(test_time_ms, 1),
            compression_ratio=round(compression, 1),
        )

# ─── DFT Coverage Analyzer ────────────────────────────────────────────────────

class DFTAnalyzer:
    def __init__(self):
        self.mbist  = MemoryBISTEngine()
        self.jtag   = JTAGEngine()
        self.atpg   = ATPGEngine()

    def analyze(self, design_name: str, technology: str,
                total_cells: int, seq_cells: int,
                memories: List[MemorySpec],
                scan_coverage_pct: float,
                bist_algo: BISTAlgorithm) -> DFTCoverage:

        # MBIST
        mbist_results = [
            self.mbist.run(m, bist_algo, seed=i*37)
            for i, m in enumerate(memories)
        ]

        # JTAG
        chain = JTAGChain(chain_id="MAIN_TAP", tap_count=4,
                          bsr_length=int(total_cells * 0.04))
        jtag_result = self.jtag.run(chain)

        # ATPG
        atpg_results = [
            self.atpg.run(total_cells, ft, scan_coverage_pct, seed=i*13)
            for i, ft in enumerate([
                FaultType.STUCK_AT_0, FaultType.STUCK_AT_1,
                FaultType.TRANSITION, FaultType.CELL_AWARE
            ])
        ]

        # Aggregate coverage
        sa_cov   = sum(r.coverage_pct for r in atpg_results[:2]) / 2
        tf_cov   = atpg_results[2].coverage_pct
        ca_cov   = atpg_results[3].coverage_pct
        overall  = (sa_cov * 0.5 + tf_cov * 0.3 + ca_cov * 0.2)

        # Observations
        obs = []
        if scan_coverage_pct < 95:
            obs.append(f"Scan coverage {scan_coverage_pct:.1f}% is below 95% target — add scan insertion to remaining logic")
        if any(r.pass_fail == "FAIL" for r in mbist_results):
            obs.append("One or more MBIST instances FAILED — check ECC configuration")
        if tf_cov < 97.0:
            obs.append(f"Transition fault coverage {tf_cov:.1f}% below 97% — add launch/capture patterns")
        if ca_cov < 95.0:
            obs.append(f"Cell-aware coverage {ca_cov:.1f}% needs improvement — review cell library models")

        # Recommendations
        recs = []
        if scan_coverage_pct < 98:
            recs.append("Increase scan chain insertion: target ≥98% scan FF ratio for production test")
        recs.append(f"Use {bist_algo.value} for memory BIST — provides {mbist_results[0].coverage_pct:.1f}% fault coverage")
        if sa_cov < 99.0:
            recs.append("Run incremental ATPG to push stuck-at coverage past 99% sign-off threshold")
        recs.append("Enable X-masking in UVM testbench to improve ATPG efficiency by ~15%")
        recs.append("Add EDT compression (target 16×) to reduce test time within ATE budget")

        return DFTCoverage(
            design_name=design_name, technology=technology,
            total_flops=seq_cells, scan_flops=int(seq_cells * scan_coverage_pct / 100),
            scan_coverage_pct=round(scan_coverage_pct, 1),
            mbist_memories=mbist_results,
            jtag_results=[jtag_result],
            atpg_results=atpg_results,
            overall_fault_coverage=round(overall, 2),
            stuck_at_coverage=round(sa_cov, 2),
            transition_coverage=round(tf_cov, 2),
            cell_aware_coverage=round(ca_cov, 2),
            observations=obs,
            recommendations=recs,
        )

# Singletons
_analyzer = DFTAnalyzer()
def get_analyzer() -> DFTAnalyzer: return _analyzer
