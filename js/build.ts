/// <reference types="node" />

import { BuildOptions, type BuildResult, build, type Metafile } from "esbuild"
import { sassPlugin } from "esbuild-sass-plugin"
import * as fs from "fs/promises"

// Parse command line arguments
const args = Object.fromEntries(
  process.argv
    .filter((arg) => arg.startsWith("--"))
    .map((arg) => {
      const [key, value] = arg.substring(2).split("=")
      return [key, value || "true"]
    }),
)

const minify = args.minify !== "false"
const metafile = args.metafile !== "false"

if (!minify) console.log("Disabling minification")
if (!metafile) console.log("Disabling metafile generation")

const outDir = "dist"

const allEsbuildMetadata: Array<Metafile> = []

function mergeMetadatas(metadatas: Array<Metafile>): Metafile {
  // Merge all the metafile objects together
  const mergedMetadata: Metafile = {
    inputs: {},
    outputs: {},
  }

  metadatas.forEach((metafile) => {
    Object.entries(metafile.inputs).forEach(([key, value]) => {
      if (
        mergedMetadata.inputs[key] &&
        JSON.stringify(mergedMetadata.inputs[key]) !== JSON.stringify(value)
      ) {
        // It's very possible for multiple MetaFile objects to refer to the same input.
        // But if that input has different values in the different Metafile objects,
        // that could cause inaccuracies when we merge them. I think it's possible they
        // could have different values if tree-shaking is enabled -- this will detect
        // those cases and warn the user, and if it happens we can figure out how to
        // handle it.
        console.error(
          `Different values found for key in metadata: ${key}. Overwriting.`,
        )
      }
      mergedMetadata.inputs[key] = value
    })
    Object.entries(metafile.outputs).forEach(([key, value]) => {
      if (mergedMetadata.outputs[key]) {
        console.error(`Duplicate key found in metadata: ${key}. Overwriting.`)
      }
      mergedMetadata.outputs[key] = value
    })
  })

  return mergedMetadata
}

async function bundle_helper(options: BuildOptions): Promise<BuildResult> {
  try {
    const result = await build({
      format: "esm",
      bundle: true,
      minify,
      // No need to clean up source maps, as `minify==false` only during `npm run watch-fast`
      // GHA will run `npm run build` which will minify
      sourcemap: minify,
      metafile,
      outdir: outDir,
      // Add Preact aliases to use Preact instead of React
      alias: {
        react: "preact/compat",
        "react-dom": "preact/compat",
        "react/jsx-runtime": "preact/jsx-runtime",
      },
      ...options,
    })

    for (const [output_file_stub] of Object.entries(
      options.entryPoints as Record<string, string>,
    )) {
      console.log(`Building ${output_file_stub}.js completed successfully!`)
    }

    if (result.metafile) {
      allEsbuildMetadata.push(result.metafile)
    }

    return result
  } catch (error) {
    console.error("Build failed:", error)
    process.exit(1) // Exit with error code to fail CI/CD pipelines
  }
}

interface EntryConfig {
  name: string
  jsEntry?: string
  sassEntry?: string
}

async function bundleEntry({
  name,
  jsEntry,
  sassEntry,
}: EntryConfig): Promise<void> {
  const tasks: Promise<BuildResult>[] = []

  if (jsEntry) {
    tasks.push(
      bundle_helper({
        entryPoints: { [name]: jsEntry },
      }),
    )
  }

  if (sassEntry) {
    tasks.push(
      bundle_helper({
        entryPoints: { [name]: sassEntry },
        plugins: [sassPlugin({ type: "css", sourceMap: false })],
      }),
    )
  }

  await Promise.all(tasks)
}

const entries: EntryConfig[] = [
  {
    name: "chat/chat",
    jsEntry: "src/chat/chat.ts",
    sassEntry: "src/chat/chat.scss",
  },
  // ShinyMarkdownStream
  {
    name: "components/markdown-stream/shiny-markdown-stream",
    jsEntry: "src/components/ShinyMarkdownStream.tsx",
    sassEntry: "src/components/MarkdownStream.css",
  },
  // MarkdownStream demo entry
  {
    name: "demo",
    jsEntry: "src/__demos__/markdown-stream/demo.tsx",
  },
  // Simple demo entry for testing
  {
    name: "demo-simple",
    jsEntry: "src/__demos__/markdown-stream/demo-simple.tsx",
  },
]

;(async () => {
  await Promise.all(entries.map(bundleEntry))

  if (metafile && allEsbuildMetadata.length > 0) {
    const mergedMetadata = mergeMetadatas(allEsbuildMetadata)
    await fs.writeFile("esbuild-metadata.json", JSON.stringify(mergedMetadata))
    console.log("Metadata file written to esbuild-metadata.json")
  }
})()
