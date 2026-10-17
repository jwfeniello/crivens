// Dump a table of function pointers at a named symbol (or hex address).
// args: <out_file> <symbol_or_hex> <count>
// @category Ghoulies
import java.io.PrintWriter;

import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.symbol.Symbol;

public class DumpTable extends GhidraScript {
    @Override
    public void run() throws Exception {
        if (!currentProgram.getName().equals("default.xbe")) {
            return;
        }
        String[] args = getScriptArgs();
        Address base = null;
        for (Symbol s : currentProgram.getSymbolTable().getSymbols(args[1])) {
            base = s.getAddress();
        }
        if (base == null) {
            base = toAddr(Long.parseLong(args[1], 16));
        }
        int n = Integer.parseInt(args[2]);
        try (PrintWriter w = new PrintWriter(args[0])) {
            w.println("table " + args[1] + " @ " + base);
            for (int i = 0; i < n; i++) {
                long ptr = getInt(base.add(4L * i)) & 0xffffffffL;
                Function f = getFunctionAt(toAddr(ptr));
                w.println(String.format("%2d %08x %s", i, ptr, f == null ? "?" : f.getName(true)));
            }
        }
        println("TABLE DONE");
    }
}
