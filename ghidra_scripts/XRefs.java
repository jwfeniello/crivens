// Print callees and callers of functions given by hex address (or containing address).
// args: <out_file> <hex_addr>...
// @category Ghoulies
import java.io.PrintWriter;

import ghidra.app.script.GhidraScript;
import ghidra.program.model.listing.Function;
import ghidra.program.model.symbol.Reference;

public class XRefs extends GhidraScript {
    @Override
    public void run() throws Exception {
        if (!currentProgram.getName().equals("default.xbe")) {
            return;
        }
        String[] args = getScriptArgs();
        try (PrintWriter w = new PrintWriter(args[0])) {
            for (int i = 1; i < args.length; i++) {
                var addr = toAddr(Long.parseLong(args[i], 16));
                Function f = getFunctionContaining(addr);
                w.println("== " + args[i] + " in " + (f == null ? "NO FUNCTION" : f.getEntryPoint() + " " + f.getName(true)));
                if (f == null) {
                    for (Reference r : getReferencesTo(addr)) {
                        w.println("   ref from " + r.getFromAddress() + " " + r.getReferenceType());
                    }
                    continue;
                }
                for (Function c : f.getCalledFunctions(monitor)) {
                    w.println("   calls  " + c.getEntryPoint() + " " + c.getName(true));
                }
                for (Function c : f.getCallingFunctions(monitor)) {
                    w.println("   called by " + c.getEntryPoint() + " " + c.getName(true));
                }
            }
        }
        println("XREFS DONE");
    }
}
