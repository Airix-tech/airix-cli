// sidecar/extract_symbols.js — usa ts-morph
let Project;
try {
  ({ Project } = require("ts-morph"));
} catch (err) {
  process.stderr.write(
    "No se pudo cargar 'ts-morph'. Ejecuta `npm install` dentro de sidecar/.\n" + err.message + "\n"
  );
  process.exit(2);
}

const target = process.argv[2];
if (!target) {
  process.stderr.write("Uso: node extract_symbols.js <ruta/al/archivo.ts>\n");
  process.exit(2);
}

try {
  const project = new Project();
  const source = project.addSourceFileAtPath(target);

  const symbols = {
    classes: source.getClasses().map(c => ({
      name: c.getName(),
      methods: c.getMethods().map(m => ({
        name: m.getName(),
        params: m.getParameters().map(p => p.getName()),
        returnType: m.getReturnType().getText(),
      })),
    })),
    interfaces: source.getInterfaces().map(i => i.getName()),
    imports: source.getImportDeclarations().map(i => i.getModuleSpecifierValue()),
    exports: source.getExportedDeclarations
      ? Array.from(source.getExportedDeclarations().keys())
      : [],
  };
  // El JSON va SOLO a stdout: cualquier diagnóstico debe ir a stderr para no
  // corromper la salida que parsea el lado Python.
  process.stdout.write(JSON.stringify(symbols));
} catch (err) {
  process.stderr.write(`Error analizando ${target}: ${err.message}\n`);
  process.exit(1);
}
