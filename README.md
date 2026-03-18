# DFTGuard ⬡ — Memory BIST · JTAG · ATPG Coverage Analyzer

> **Hero project for NVIDIA DFT Team applications**
> Memory BIST · JTAG Boundary Scan · ATPG · UVM Testplan · FastAPI · Login/Signup

---

## What It Does
- **Memory BIST** — March-C/CM/LR/GALPAT algorithm simulation, ECC SECDED verification
- **JTAG** — IEEE 1149.1 boundary scan, BSR testing, IDCODE verification
- **ATPG** — Stuck-at, Transition, Cell-aware, Bridging fault coverage analysis
- **UVM Testplan** — auto-generates P0/P1 test cases with coverage targets
- **Fault Coverage Analytics** — per-fault-model breakdown + compression ratios
- **Auth** — full signup/login/logout with persistent sessions

## NVIDIA DFT JD Keywords Matched
| JD Requirement | DFTGuard Feature |
|----------------|-----------------|
| "Memory BIST logic" | March-C/CM/LR/GALPAT engines |
| "JTAG, IO BIST" | IEEE 1149.1 BSR + IDCODE |
| "ATPG" | Stuck-at + Transition + Cell-aware |
| "UVM testplan development" | Auto-generated P0/P1 test cases |
| "Coverage metrics" | Overall/SA/TF/CA breakdown |
| "Pre-silicon simulation" | Fault injection simulation |
| "Standard coverage metrics" | Per-instance pass/fail criteria |

## Stack
| Layer | Tech |
|-------|------|
| BIST Engine | Python (DFT algorithms) |
| Backend | FastAPI + JWT Auth |
| Frontend | Full SPA with Login/Signup + Dashboard |
| Deploy | Vercel + Render + Docker |

## Run Locally
```bash
cd backend && pip install -r requirements.txt
uvicorn main:app --reload --port 8000
# Open frontend/dftguard.html
```

## Push to GitHub
```powershell
cd C:\Users\soumy\Downloads\dftguard_fullproject
git init
git add .
git commit -m "feat: DFTGuard Memory BIST JTAG ATPG coverage analyzer"
git branch -M main
git remote add origin https://github.com/Divinesoumyadip/dftguard-dft-analyzer.git
git push -u origin main
```
