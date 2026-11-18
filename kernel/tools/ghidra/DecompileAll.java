import ghidra.app.script.GhidraScript;
import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileOptions;
import ghidra.app.decompiler.DecompileResults;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.FunctionIterator;

import java.io.File;
import java.io.FileWriter;
import java.io.PrintWriter;

// Headless bulk decompiler: writes one pseudo-C file per function plus _index.tsv.
// Usage: -postScript DecompileAll.java <outputDir> [nameRegex]   (regex: only functions whose name matches)
public class DecompileAll extends GhidraScript {

	@Override
	public void run() throws Exception {
		String outDirArg = getScriptArgs().length > 0 ? getScriptArgs()[0] : "decompiled";
		java.util.regex.Pattern filter = getScriptArgs().length > 1 ? java.util.regex.Pattern.compile(getScriptArgs()[1]) : null;
		File outDir = new File(outDirArg);
		outDir.mkdirs();

		DecompInterface di = new DecompInterface();
		di.setOptions(new DecompileOptions());
		if (!di.openProgram(currentProgram)) {
			println("FATAL: could not open decompiler: " + di.getLastMessage());
			return;
		}

		PrintWriter index = new PrintWriter(new FileWriter(new File(outDir, "_index.tsv")));
		index.println("name\taddress\tbytes\tfile\tstatus");

		long count = 0, skipped = 0, failed = 0;
		FunctionIterator it = currentProgram.getFunctionManager().getFunctions(true);
		while (it.hasNext()) {
			if (monitor.isCancelled()) {
				index.println("# cancelled");
				break;
			}
			Function f = it.next();
			if (f.isThunk()) { skipped++; continue; }
			if (filter != null && !filter.matcher(f.getName()).find()) continue;

			count++;
			String addr = f.getEntryPoint().toString();
			String safeName = f.getName().replaceAll("[^A-Za-z0-9_.$-]", "_");
			String fname = safeName + "_" + addr + ".c";
			String status = "ok";
			try {
				DecompileResults res = di.decompileFunction(f, 60, monitor);
				String code = (res != null && res.getDecompiledFunction() != null)
					? res.getDecompiledFunction().getC() : null;
				if (code != null) {
					PrintWriter pw = new PrintWriter(new FileWriter(new File(outDir, fname)));
					pw.println("// " + f.getName() + " @ " + f.getEntryPoint());
					pw.print(code);
					pw.close();
				} else {
					status = "no_output";
					failed++;
				}
			} catch (Exception e) {
				status = "error:" + e.getClass().getSimpleName();
				failed++;
			}
			index.println(f.getName() + "\t" + addr + "\t" +
				f.getBody().getNumAddresses() + "\t" +
				(status.equals("ok") ? fname : "") + "\t" + status);

			if (count % 250 == 0) {
				index.flush();
				println("progress: " + count + " decompiled, " + failed + " failed, " + skipped + " thunks skipped");
			}
		}
		index.close();
		di.dispose();
		println("DONE: " + count + " functions, " + failed + " failed, " + skipped + " thunks skipped");
	}
}
