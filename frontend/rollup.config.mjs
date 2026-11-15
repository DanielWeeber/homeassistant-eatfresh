import resolve from "@rollup/plugin-node-resolve";
import terser from "@rollup/plugin-terser";
import typescript from "@rollup/plugin-typescript";

// Two self-contained files: the sidebar panel and the dashboard cards.
const bundle = (input, file) => ({
  input,
  output: {
    file: `../custom_components/eatfresh/frontend/${file}`,
    format: "es",
    inlineDynamicImports: true,
    sourcemap: false,
  },
  plugins: [
    resolve({ browser: true }),
    typescript({ tsconfig: "./tsconfig.json" }),
    terser({ ecma: 2022, module: true, format: { comments: false } }),
  ],
});

export default [
  bundle("src/eatfresh-panel.ts", "eatfresh-panel.js"),
  bundle("src/eatfresh-cards.ts", "eatfresh-cards.js"),
];
