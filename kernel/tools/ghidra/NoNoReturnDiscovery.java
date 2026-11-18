import ghidra.app.script.GhidraScript;
// Pre-script: disable non-returning-function discovery (it wrongly marks printk noreturn on this kernel,
// truncating every function at its first printk).
public class NoNoReturnDiscovery extends GhidraScript {
	@Override
	public void run() throws Exception {
		setAnalysisOption(currentProgram, "Non-Returning Functions - Discovered", "false");
		println("disabled: Non-Returning Functions - Discovered");
	}
}
