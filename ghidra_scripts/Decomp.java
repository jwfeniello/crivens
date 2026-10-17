// Decompile functions (by hex address or name) in default.xbe and write C to a file.
// args: <out_file> <addr_or_name>...
// @category Ghoulies
import java.io.PrintWriter;

import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;

public class Decomp extends GhidraScript {
    @Override
    public void run() throws Exception {
        if (!currentProgram.getName().equals("default.xbe")) {
            return;
        }
        String[] args = getScriptArgs();
        DecompInterface di = new DecompInterface();
        di.openProgram(currentProgram);
        try (PrintWriter w = new PrintWriter(args[0])) {
            for (int i = 1; i < args.length; i++) {
                Function f = null;
                try {
                    Address a = toAddr(Long.parseLong(args[i], 16));
                    f = getFunctionAt(a);
                } catch (NumberFormatException e) {
                    for (Function g : currentProgram.getFunctionManager().getFunctions(true)) {
                        if (g.getName(true).equals(args[i]) || g.getName().equals(args[i])) {
                            f = g;
                            break;
                        }
                    }
                }
                if (f == null) {
                    w.println("// NOT FOUND " + args[i]);
                    continue;
                }
                DecompileResults r = di.decompileFunction(f, 120, monitor);
                w.println("// ===== " + f.getEntryPoint() + " " + f.getName(true));
                w.println(r.decompileCompleted() ? r.getDecompiledFunction().getC() : "// decompile failed: " + r.getErrorMessage());
            }
        }
        println("DECOMPILED " + (args.length - 1));
    }
}
