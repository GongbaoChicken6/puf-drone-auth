# A1 Implementation Plan: Unify R2 Verification Algorithm

## 1. Problem

FPGA expects R2 = ~C2 (trivially predictable).
PC generates R2 = HMAC-SHA256(key, C2) (crypto-secure but FPGA can't implement).
These DON'T MATCH. First real communication will always fail.

## 2. Selected Approach: PUF-derived Key + Non-linear Mixing

Algorithm (both sides compute identically):
  K[0..7] = 8-byte device key (extracted from PUF stable bits at enrollment)
  C2[0..7] = 8-byte counter-challenge (increments per auth, anti-replay)

  For each byte i = 0..7:
    idx1 = (i + C2[0]) % 8
    idx2 = (i + C2[1]) % 8
    idx3 = (i + 3) % 8
    R2[i] = K[idx1] XOR C2[i] XOR K[idx2] AND_BITWISE (C2[i] AND K[idx3])

Security properties:
- Replay old R2: C2 changed -> indices changed -> old R2 mismatches
- Forged base station (no K): 2^64 possible keys, brute force infeasible
- Eavesdrop (C2,R2) pairs: AND non-linearity prevents linear solve for K
- No pre-shared keys: K derived from PUF at enrollment, not factory-loaded

## 3. Implementation Steps

### Step 1: Modify terminal_fsm.v (~30 lines)
- Add device_key[0:7] register (test value for now, PUF-derived in W4)
- Replace r2_expected calculation with non-linear function
- Use Verilog function (synthesizes to combinational logic, ~20 LUT)

### Step 2: Modify hsm.py (~10 lines)  
- Replace SimulatedHSM.respond() from HMAC to matching algorithm
- Keep same interface (respond(c2) -> bytes)

### Step 3: Generate test vectors
- Python script generates (K, C2, expected_R2) triples
- Used for both Python unit tests and Verilog TB golden vectors

### Step 4: Update testbenches
- tb_terminal_fsm.v: update RESULT frame R2 values
- tb_level3_protocol.v: update golden vector bytes
- Run full 10-TB regression

### Step 5: Update documentation
- protocol_contract.md: R2 algorithm definition
- project_design.md: W3 status update

## 4. Verification

1. Python standalone: compute R2 for known (K, C2), verify against hand-calculation
2. Cross-language: Python and Verilog produce identical R2 for same inputs
3. Integration: tb_level3 full protocol flow with new R2
4. Regression: all 10 TB suites pass

## 5. Timeline: ~2 hours total

See security analysis in conversation for 5-option comparison table.