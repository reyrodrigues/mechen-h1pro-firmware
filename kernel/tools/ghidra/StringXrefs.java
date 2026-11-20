// Decompile every function that references a string matching a regex.
// Usage: -postScript StringXrefs.java <outfile> <regex>
import ghidra.app.script.GhidraScript;
import ghidra.app.decompiler.*;
import ghidra.program.model.listing.*;
import ghidra.program.model.symbol.*;
import java.io.*;
import java.util.*;
import java.util.regex.*;

public class StringXrefs extends GhidraScript {
    @Override
    public void run() throws Exception {
        String[] a = getScriptArgs();
        PrintWriter out = new PrintWriter(new FileWriter(a[0]));
        Pattern re = Pattern.compile(a[1]);
        DecompInterface d = new DecompInterface();
        d.openProgram(currentProgram);
        Set<Function> done = new LinkedHashSet<>();
        // Raw binaries have few defined strings: define one at every NUL-terminated match first.
        byte[] all = new byte[(int) currentProgram.getMemory().getBlocks()[0].getSize()];
        ghidra.program.model.address.Address base = currentProgram.getMemory().getBlocks()[0].getStart();
        currentProgram.getMemory().getBytes(base, all);
        String text = new String(all, "ISO-8859-1");
        Matcher m0 = re.matcher(text);
        List<Data> hits = new ArrayList<>();
        while (m0.find()) {
            int st = text.lastIndexOf('\0', m0.start()) + 1;
            ghidra.program.model.address.Address ad = base.add(st);
            Data dd = getDataAt(ad);
            if (dd == null) { clearListing(ad, ad.add(text.indexOf('\0', st) - st)); dd = createAsciiString(ad); }
            hits.add(dd);
        }
        for (Data s : hits) {
            String v = String.valueOf(s.getValue());
            for (Reference r : getReferencesTo(s.getAddress())) {
                Function f = getFunctionContaining(r.getFromAddress());
                out.printf("STR %s \"%s\" <- %s in %s%n", s.getAddress(), v, r.getFromAddress(),
                           f == null ? "?" : f.getName() + "@" + f.getEntryPoint());
                if (f != null) done.add(f);
            }
        }
        for (Function f : done) {
            DecompileResults res = d.decompileFunction(f, 60, monitor);
            out.printf("%n==== %s @ %s%n%s%n", f.getName(), f.getEntryPoint(),
                       res.decompileCompleted() ? res.getDecompiledFunction().getC() : "(failed)");
        }
        out.close();
    }
}
