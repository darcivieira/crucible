import * as vscode from "vscode";
import { spawn } from "child_process";

export function activate(context: vscode.ExtensionContext) {
  context.subscriptions.push(
    vscode.commands.registerCommand("crucible.validate", () => runCrucible("validate")),
    vscode.commands.registerCommand("crucible.optimize", () => runCrucible("optimize")),
    vscode.commands.registerCommand("crucible.serve", () => runCrucible("serve")),
  );
}

export function deactivate() {}

function runCrucible(action: "validate" | "optimize" | "serve") {
  const workspace = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
  if (!workspace) {
    vscode.window.showErrorMessage("Open a workspace before running Crucible.");
    return;
  }

  const config = vscode.workspace.getConfiguration("crucible");
  const commandPrefix = config.get<string>("command", "uv run crucible");
  const configPath = config.get<string>("configPath", "config.yaml");
  const promptPath = config.get<string>("promptPath", "prompt.txt");
  const gabaritoPath = config.get<string>("gabaritoPath", "gabarito.yaml");
  const args =
    action === "validate"
      ? ["validate", "--prompt", promptPath, "--gabarito", gabaritoPath, "--config", configPath]
      : action === "optimize"
        ? ["optimize", "--config", configPath]
        : ["serve"];

  const [command, ...prefixArgs] = splitCommand(commandPrefix);
  const output = vscode.window.createOutputChannel("Crucible");
  output.show(true);
  output.appendLine(`$ ${[command, ...prefixArgs, ...args].join(" ")}`);

  const child = spawn(command, [...prefixArgs, ...args], { cwd: workspace, shell: true });
  child.stdout.on("data", (chunk) => output.append(chunk.toString()));
  child.stderr.on("data", (chunk) => output.append(chunk.toString()));
  child.on("close", (code) => {
    if (code === 0) {
      vscode.window.showInformationMessage(`Crucible ${action} completed.`);
    } else {
      vscode.window.showErrorMessage(`Crucible ${action} failed with exit code ${code}.`);
    }
  });
}

function splitCommand(command: string): string[] {
  return command.match(/(?:[^\s"]+|"[^"]*")+/g)?.map((part) => part.replace(/^"|"$/g, "")) ?? [];
}
