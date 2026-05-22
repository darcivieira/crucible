import * as vscode from "vscode";
import { spawn, ChildProcessWithoutNullStreams } from "child_process";
import * as path from "path";

let dashboardProcess: ChildProcessWithoutNullStreams | undefined;

export function activate(context: vscode.ExtensionContext) {
  context.subscriptions.push(
    vscode.commands.registerCommand("crucible.validate", () => runCrucible("validate")),
    vscode.commands.registerCommand("crucible.optimize", () => runCrucible("optimize")),
    vscode.commands.registerCommand("crucible.openDashboard", () => openDashboard(context)),
    vscode.commands.registerCommand("crucible.openLatestReport", () => openLatestReport()),
    vscode.commands.registerCommand("crucible.selectFiles", () => selectFiles()),
  );
}

export function deactivate() {
  dashboardProcess?.kill();
}

function runCrucible(action: "validate" | "optimize") {
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
      : ["optimize", "--config", configPath, "--prompt", promptPath, "--gabarito", gabaritoPath];

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

async function selectFiles() {
  const workspace = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
  if (!workspace) {
    vscode.window.showErrorMessage("Open a workspace before configuring Crucible.");
    return;
  }

  const prompt = await pickFile(workspace, "Select prompt file");
  if (!prompt) return;
  const gabarito = await pickFile(workspace, "Select gabarito file");
  if (!gabarito) return;
  const config = await pickFile(workspace, "Select config file");
  if (!config) return;

  const settings = vscode.workspace.getConfiguration("crucible");
  await settings.update("promptPath", relative(workspace, prompt), vscode.ConfigurationTarget.Workspace);
  await settings.update("gabaritoPath", relative(workspace, gabarito), vscode.ConfigurationTarget.Workspace);
  await settings.update("configPath", relative(workspace, config), vscode.ConfigurationTarget.Workspace);
  vscode.window.showInformationMessage("Crucible files configured for this workspace.");
}

async function openDashboard(context: vscode.ExtensionContext) {
  const workspace = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
  if (!workspace) {
    vscode.window.showErrorMessage("Open a workspace before running Crucible.");
    return;
  }
  if (!dashboardProcess || dashboardProcess.killed) {
    dashboardProcess = spawnCrucible("serve", [], workspace, "Dashboard");
    context.subscriptions.push({ dispose: () => dashboardProcess?.kill() });
  }
  await vscode.env.openExternal(vscode.Uri.parse("http://127.0.0.1:7777"));
}

async function openLatestReport() {
  const workspace = vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
  if (!workspace) {
    vscode.window.showErrorMessage("Open a workspace before running Crucible.");
    return;
  }
  const output = vscode.window.createOutputChannel("Crucible");
  const child = spawnCrucible("report", ["--run", "latest", "--format", "html"], workspace, "Report", output);
  let stdout = "";
  child.stdout.on("data", (chunk) => {
    stdout += chunk.toString();
  });
  child.on("close", async (code) => {
    if (code !== 0) {
      vscode.window.showErrorMessage(`Crucible report failed with exit code ${code}.`);
      return;
    }
    const reportPath = stdout.trim().split(/\r?\n/).at(-1);
    if (!reportPath) {
      vscode.window.showErrorMessage("Crucible did not return a report path.");
      return;
    }
    await vscode.env.openExternal(vscode.Uri.file(path.resolve(workspace, reportPath)));
  });
}

function spawnCrucible(
  commandName: string,
  args: string[],
  workspace: string,
  label: string,
  output = vscode.window.createOutputChannel("Crucible"),
): ChildProcessWithoutNullStreams {
  const commandPrefix = vscode.workspace.getConfiguration("crucible").get<string>("command", "uv run crucible");
  const [command, ...prefixArgs] = splitCommand(commandPrefix);
  output.show(true);
  output.appendLine(`$ ${[command, ...prefixArgs, commandName, ...args].join(" ")}`);
  const child = spawn(command, [...prefixArgs, commandName, ...args], { cwd: workspace, shell: true });
  child.stdout.on("data", (chunk) => output.append(chunk.toString()));
  child.stderr.on("data", (chunk) => output.append(chunk.toString()));
  child.on("error", (error) => {
    vscode.window.showErrorMessage(`Crucible ${label} failed: ${error.message}`);
  });
  return child;
}

async function pickFile(workspace: string, title: string): Promise<string | undefined> {
  const [file] = await vscode.window.showOpenDialog({
    title,
    defaultUri: vscode.Uri.file(workspace),
    canSelectFiles: true,
    canSelectFolders: false,
    canSelectMany: false,
  }) ?? [];
  return file?.fsPath;
}

function relative(workspace: string, file: string): string {
  return path.relative(workspace, file);
}

function splitCommand(command: string): string[] {
  return command.match(/(?:[^\s"]+|"[^"]*")+/g)?.map((part) => part.replace(/^"|"$/g, "")) ?? [];
}
