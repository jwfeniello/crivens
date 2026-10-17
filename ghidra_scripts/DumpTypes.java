// Dump struct layouts (offset, size, type, name) for named data types.
// args: <out_file> <type_name>...
// @category Ghoulies
import java.io.PrintWriter;
import java.util.ArrayList;
import java.util.Iterator;
import java.util.List;

import ghidra.app.script.GhidraScript;
import ghidra.program.model.data.Composite;
import ghidra.program.model.data.DataType;
import ghidra.program.model.data.DataTypeComponent;
import ghidra.program.model.data.Enum;

public class DumpTypes extends GhidraScript {
    @Override
    public void run() throws Exception {
        if (!currentProgram.getName().equals("default.xbe")) {
            return;
        }
        String[] args = getScriptArgs();
        try (PrintWriter w = new PrintWriter(args[0])) {
            for (int i = 1; i < args.length; i++) {
                List<DataType> found = new ArrayList<>();
                currentProgram.getDataTypeManager().findDataTypes(args[i], found);
                if (found.isEmpty()) {
                    w.println("// NOT FOUND " + args[i]);
                }
                for (DataType dt : found) {
                    w.println("// " + dt.getPathName() + " size=0x" + Integer.toHexString(dt.getLength()));
                    if (dt instanceof Composite c) {
                        for (DataTypeComponent comp : c.getDefinedComponents()) {
                            w.println(String.format("  +0x%03x [0x%x] %-28s %s", comp.getOffset(), comp.getLength(),
                                comp.getDataType().getName(), comp.getFieldName()));
                        }
                    } else if (dt instanceof Enum e) {
                        for (String n : e.getNames()) {
                            w.println("  " + n + " = 0x" + Long.toHexString(e.getValue(n)));
                        }
                    }
                }
            }
        }
        println("DUMPED");
    }
}
