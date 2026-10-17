// Lists user-named functions (non FUN_) in the current program to a text file.
// @category Ghoulies
import java.io.PrintWriter;

import ghidra.app.script.GhidraScript;
import ghidra.program.model.listing.Function;
import ghidra.program.model.symbol.SourceType;

public class ListNamed extends GhidraScript {
    @Override
    public void run() throws Exception {
        String out = getScriptArgs().length > 0 ? getScriptArgs()[0] : "named.txt";
        int total = 0, named = 0;
        try (PrintWriter w = new PrintWriter(out)) {
            w.println("# program " + currentProgram.getName() + " " + currentProgram.getExecutablePath());
            for (Function f : currentProgram.getFunctionManager().getFunctions(true)) {
                total++;
                if (f.getSymbol().getSource() == SourceType.USER_DEFINED || !f.getName().startsWith("FUN_")) {
                    named++;
                    w.println(f.getEntryPoint() + " " + f.getName(true) + " | " + f.getSignature().getPrototypeString());
                }
            }
            w.println("# total " + total + " named " + named);
        }
        println("LISTED " + named + "/" + total);
    }
}
