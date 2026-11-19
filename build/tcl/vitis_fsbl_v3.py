import vitis
import os, time, sys

XSA = r"D:\puf-drone-auth\build\qspi_xsa_v3\zc706_qspi_v3.xsa"
ts = time.strftime("%H%M%S")
out = rf"D:\puf-drone-auth\build\vitis_qspi3_{ts}"
os.makedirs(out, exist_ok=True)
print("WS=" + out, flush=True)
assert os.path.exists(XSA), "XSA missing: " + XSA
assert os.path.getsize(XSA) > 100000, "XSA degenerate, abort"

client = vitis.create_client()
client.set_workspace(path=out)
print("WORKSPACE_SET", flush=True)

platform = client.create_platform_component(
    name="zc706_qspi",
    hw_design=XSA,
    os="standalone",
    cpu="ps7_cortexa9_0",
    domain_name="standalone_ps7_cortexa9_0",
    template="zynq_fsbl",
)
print("PLATFORM_CREATED", flush=True)

platform.build()
print("PLATFORM_BUILD_OK", flush=True)

for root, dirs, files in os.walk(out):
    for f in files:
        if f.endswith(".elf"):
            p = os.path.join(root, f)
            print("ELF: %s (%d bytes)" % (p, os.path.getsize(p)), flush=True)
print("SCRIPT_END", flush=True)
