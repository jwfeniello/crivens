// Dump all composite/enum data types whose name contains any of the given substrings.
// args: <out_file> <substring>...
// @category Ghoulies
import java.io.PrintWriter;
import java.util.Iterator;

import ghidra.app.script.GhidraScript;
import ghidra.program.model.data.Composite;
import ghidra.program.model.data.DataType;
import ghidra.program.model.data.DataTypeComponent;
import ghidra.program.model.data.Enum;

public class DumpTypesLike extends GhidraScript {
    @Override
    public void run() throws Exception {
        if (!currentProgram.getName().equals("default.xbe")) {
            return;
        }
        String[] args = getScriptArgs();
        try (PrintWriter w = new PrintWriter(args[0])) {
            Iterator<DataType> it = currentProgram.getDataTypeManager().getAllDataTypes();
            while (it.hasNext()) {
                DataType dt = it.next();
                boolean match = false;
                for (int i = 1; i < args.length; i++) {
                    match |= dt.getName().contains(args[i]);
                }
                if (!match || !(dt instanceof Composite || dt instanceof Enum)) {
                    continue;
                }
                w.println("// " + dt.getPathName() + " size=0x" + Integer.toHexString(dt.getLength()));
                if (dt instanceof Composite c) {
                    for (DataTypeComponent comp : c.getDefinedComponents()) {
                        w.println(String.format("  +0x%03x [0x%x] %-30s %s", comp.getOffset(), comp.getLength(),
                            comp.getDataType().getName(), comp.getFieldName()));
                    }
                } else {
                    Enum e = (Enum) dt;
                    for (long v : e.getValues()) {
                        w.println(String.format("  0x%02x %s", v, e.getName(v)));
                    }
                }
            }
        }
        println("TYPES DONE");
    }
}
