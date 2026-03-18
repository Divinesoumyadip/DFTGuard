"""
DFTGuard Backend — Memory BIST / JTAG / ATPG Coverage Analyzer
FastAPI + JWT Auth + UVM testplan generation
"""
from __future__ import annotations
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'bist_engine'))

import uuid, hashlib, random
from datetime import datetime
from typing import Dict, List, Optional
from dft_engine import (
    MemorySpec, BISTAlgorithm, FaultType, DFTAnalyzer,
    BISTResult, JTAGResult, ATPGResult, DFTCoverage
)
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer
from pydantic import BaseModel

app = FastAPI(title="DFTGuard API", version="1.2.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# ─── In-memory store ──────────────────────────────────────────────────────────
USERS: Dict[str, dict] = {}
SESSIONS: Dict[str, str] = {}
HISTORY: Dict[str, list] = {}
analyzer = DFTAnalyzer()

# ─── Auth ─────────────────────────────────────────────────────────────────────
class SignupReq(BaseModel):
    name: str; email: str; password: str

class LoginReq(BaseModel):
    email: str; password: str

class AuthResp(BaseModel):
    token: str; user_id: str; name: str; email: str

def hash_pw(p: str) -> str:
    return hashlib.sha256(p.encode()).hexdigest()

def make_token() -> str:
    return str(uuid.uuid4()).replace('-', '')

def current_user(token: str = Depends(OAuth2PasswordBearer(tokenUrl="/api/auth/login-form"))) -> dict:
    uid = SESSIONS.get(token)
    if not uid or uid not in USERS:
        raise HTTPException(401, "Invalid token")
    return USERS[uid]

@app.post("/api/auth/signup", response_model=AuthResp)
def signup(req: SignupReq):
    if any(u['email'] == req.email for u in USERS.values()):
        raise HTTPException(400, "Email already registered")
    uid = str(uuid.uuid4())[:8]
    token = make_token()
    USERS[uid] = {"user_id": uid, "name": req.name, "email": req.email,
                  "password_hash": hash_pw(req.password),
                  "joined_at": datetime.utcnow().isoformat()}
    SESSIONS[token] = uid
    HISTORY[uid] = []
    return AuthResp(token=token, user_id=uid, name=req.name, email=req.email)

@app.post("/api/auth/login", response_model=AuthResp)
def login(req: LoginReq):
    user = next((u for u in USERS.values() if u['email'] == req.email), None)
    if not user or user['password_hash'] != hash_pw(req.password):
        raise HTTPException(401, "Invalid credentials")
    token = make_token()
    SESSIONS[token] = user['user_id']
    return AuthResp(token=token, user_id=user['user_id'], name=user['name'], email=user['email'])

# ─── DFT Analysis Models ──────────────────────────────────────────────────────
class MemoryInput(BaseModel):
    name: str = "SRAM_512x32"; depth: int = 512; width: int = 32
    num_ports: int = 1; has_ecc: bool = True

class AnalyzeRequest(BaseModel):
    design_name: str = "riscv_core"
    technology: str = "sky130"
    total_cells: int = 5000
    seq_cells: int = 800
    scan_coverage_pct: float = 96.5
    bist_algorithm: str = "March-C"
    memories: List[MemoryInput] = []

class AnalyzeResponse(BaseModel):
    analysis_id: str
    design_name: str
    technology: str
    total_flops: int
    scan_flops: int
    scan_coverage_pct: float
    overall_fault_coverage: float
    stuck_at_coverage: float
    transition_coverage: float
    cell_aware_coverage: float
    mbist_results: list
    jtag_results: list
    atpg_results: list
    uvm_testplan: list
    observations: List[str]
    recommendations: List[str]
    analyzed_at: str

def build_uvm_testplan(cov: DFTCoverage) -> list:
    plan = []
    for mem in cov.mbist_memories:
        plan.append({
            "test_name": f"mbist_{mem.memory_name.lower()}",
            "type": "Memory-BIST",
            "algorithm": mem.algorithm,
            "expected_coverage": f"{mem.coverage_pct}%",
            "priority": "P0",
            "mode": "MBIST",
            "pass_criteria": "coverage >= 99.0% AND uncorrectable_errors == 0"
        })
    for r in cov.atpg_results:
        plan.append({
            "test_name": f"atpg_{r.fault_type.lower().replace('-','_').replace(' ','_')}",
            "type": "ATPG",
            "fault_model": r.fault_type,
            "pattern_count": r.pattern_count,
            "expected_coverage": f"{r.coverage_pct}%",
            "priority": "P0" if "stuck" in r.fault_type.lower() else "P1",
            "mode": "Scan",
            "pass_criteria": f"coverage >= {'99' if 'stuck' in r.fault_type.lower() else '97'}%"
        })
    plan.append({
        "test_name": "jtag_boundary_scan",
        "type": "JTAG",
        "algorithm": "IEEE 1149.1",
        "expected_coverage": f"{cov.jtag_results[0].coverage_pct}%",
        "priority": "P0",
        "mode": "JTAG",
        "pass_criteria": "connectivity_pass AND idcode_correct"
    })
    return plan

@app.get("/api/health")
def health():
    return {"status": "ok", "timestamp": datetime.utcnow().isoformat()}

@app.post("/api/analyze", response_model=AnalyzeResponse)
def analyze(req: AnalyzeRequest, user: dict = Depends(current_user)):
    algo_map = {
        "March-C": BISTAlgorithm.MARCH_C,
        "March-CM": BISTAlgorithm.MARCH_CM,
        "MATS+": BISTAlgorithm.MATS_PLUS,
        "GALPAT": BISTAlgorithm.GALPAT,
        "March-LR": BISTAlgorithm.MARCH_LR,
    }
    algo  = algo_map.get(req.bist_algorithm, BISTAlgorithm.MARCH_C)
    mems  = [MemorySpec(m.name, m.depth, m.width, m.num_ports, m.has_ecc) for m in req.memories] or [
        MemorySpec("SRAM_512x32", 512, 32, 1, True),
        MemorySpec("SRAM_256x64", 256, 64, 2, True),
        MemorySpec("ROM_1Kx8",   1024,  8, 1, False),
    ]
    cov   = analyzer.analyze(req.design_name, req.technology, req.total_cells,
                             req.seq_cells, mems, req.scan_coverage_pct, algo)
    plan  = build_uvm_testplan(cov)
    aid   = str(uuid.uuid4())[:8]
    HISTORY.setdefault(user['user_id'], []).append({
        "id": aid, "design": req.design_name,
        "coverage": cov.overall_fault_coverage,
        "at": datetime.utcnow().isoformat()
    })
    return AnalyzeResponse(
        analysis_id=aid, design_name=req.design_name,
        technology=req.technology, total_flops=cov.total_flops,
        scan_flops=cov.scan_flops, scan_coverage_pct=cov.scan_coverage_pct,
        overall_fault_coverage=cov.overall_fault_coverage,
        stuck_at_coverage=cov.stuck_at_coverage,
        transition_coverage=cov.transition_coverage,
        cell_aware_coverage=cov.cell_aware_coverage,
        mbist_results=[vars(r) for r in cov.mbist_memories],
        jtag_results=[vars(r) for r in cov.jtag_results],
        atpg_results=[{"fault_type": r.fault_type, "total_faults": r.total_faults,
                       "detected_faults": r.detected_faults, "coverage_pct": r.coverage_pct,
                       "pattern_count": r.pattern_count, "compression_ratio": r.compression_ratio,
                       "test_time_ms": r.test_time_ms} for r in cov.atpg_results],
        uvm_testplan=plan,
        observations=cov.observations, recommendations=cov.recommendations,
        analyzed_at=datetime.utcnow().isoformat()
    )

@app.get("/api/history")
def history(user: dict = Depends(current_user)):
    return {"analyses": HISTORY.get(user['user_id'], [])}

@app.get("/api/presets")
def presets():
    return {"presets": [
        {"name":"RISC-V Core","tech":"sky130","total_cells":5000,"seq_cells":800,"scan_pct":96.5,"algo":"March-C"},
        {"name":"GPU Shader Block","tech":"7nm","total_cells":280000,"seq_cells":42000,"scan_pct":98.2,"algo":"March-CM"},
        {"name":"AI Accelerator","tech":"5nm","total_cells":850000,"seq_cells":120000,"scan_pct":99.1,"algo":"GALPAT"},
        {"name":"Mobile SoC","tech":"16nm","total_cells":180000,"seq_cells":28000,"scan_pct":97.8,"algo":"March-LR"},
    ]}
