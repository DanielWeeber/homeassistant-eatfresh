import resolve from "@rollup/plugin-node-resolve";
import terser from "@rollup/plugin-terser";
import typescript from "@rollup/plugin-typescript";

export default {
  input: "src/eatfresh-panel.ts",
  output: {
    file: "../custom_components/eatfresh/frontend/eatfresh-panel.js",
    format: "es",
    inlineDynamicImports: true,
    sourcemap: false,
  },
  plugins: [
    resolve({ browser: true }),
    typescript({ tsconfig: "./tsconfig.json" }),
    terser({ ecma: 2022, module: true, format: { comments: false } }),
  ],
};
