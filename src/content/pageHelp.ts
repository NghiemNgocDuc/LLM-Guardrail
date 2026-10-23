export type PageHelp = {
  title: string;
  description: string;
  steps: string[];
  tip: string;
  action: { label: string; view: string };
};

export const PAGE_HELP: Record<string, PageHelp> = {
  dashboard: {
    title: "Understand your overview",
    description: "See how much AI model traffic your workspace handles and which requests need a closer look.",
    steps: [
      "Choose a time period to compare requests, blocked traffic, response time, and token use.",
      "Look at triggered rules to understand which policies are affecting requests.",
      "Open Request logs to investigate a blocked or failed request.",
    ],
    tip: "An empty overview is normal before your first gateway request. Start with an everyday prompt in the playground.",
    action: { label: "Try your first prompt", view: "chat" },
  },
  chat: {
    title: "Try an AI request",
    description: "The playground lets you send a prompt and see the model response alongside the checks that ran.",
    steps: [
      "Choose an example or write a short prompt. Your signed-in session is enough to get started.",
      "Select Run prompt, then read the input and output policy decisions in the response inspector.",
      "Expand Request details to see the model, response time, and request identifier.",
    ],
    tip: "Client blocked means the browser stopped the prompt before sending it to the gateway. Provider keys belong on the server; only grg_ gateway keys can be entered here.",
    action: { label: "Explore request logs", view: "logs" },
  },
  skills: {
    title: "Review agent instructions",
    description: "Skill Guard checks the instructions an AI agent will follow and helps you review possible risks.",
    steps: [
      "Paste or upload a skill file to scan it, then read each finding and its explanation.",
      "Use managed skills to edit saved instructions and check for policy conflicts before sharing them.",
      "Review rejected access cases before choosing whether to keep them blocked or allow access.",
    ],
    tip: "The scanner uses heuristics and can miss risks or flag safe text. Saving a managed draft does not approve delivery; downloads and live access still check policy.",
    action: { label: "Review workspace policies", view: "policy" },
  },
  memory: {
    title: "Keep useful context",
    description: "Save facts, preferences, and procedures that can help with future AI requests.",
    steps: [
      "Create a memory, or extract suggestions from your last playground chat and review them before saving.",
      "Pin the context you want included whenever chat context is assembled.",
      "Search or use Recall to find relevant memories. Edit or archive anything that is out of date.",
    ],
    tip: "Keep memories specific and current. A confidence score describes a saved memory; it does not prove that its contents are correct.",
    action: { label: "Open the playground", view: "chat" },
  },
  mandate: {
    title: "See how permissions keep their context",
    description: "MandateFlow is a guided demo of how an agent's access depends on where a reference came from.",
    steps: [
      "Run the 10-call demo to compare a support reference with an anonymous payment reference.",
      "Follow the execution trace to see which tool calls are allowed, denied, or retried.",
      "Read the evidence receipt to compare the expected result with the calls that reached the demo service.",
    ],
    tip: "This uses demo fixtures. Its results explain the permission flow; they do not measure every workflow in your application.",
    action: { label: "Learn about the project", view: "about" },
  },
  analytics: {
    title: "Understand your AI traffic",
    description: "Compare usage over time and see which rules, providers, and models account for your traffic.",
    steps: [
      "Select a reporting period and review request volume, outcomes, and token use.",
      "Compare triggered rules and model usage to spot changes worth investigating.",
      "Export a CSV when you need to review the figures outside this workspace.",
    ],
    tip: "Not delivered includes blocked, rate-limited, and failed requests. Open Request logs to find the reason for an individual outcome.",
    action: { label: "Investigate request logs", view: "logs" },
  },
  logs: {
    title: "Find out what happened to a request",
    description: "Request logs record gateway outcomes so you can investigate a block, an error, or a slow response.",
    steps: [
      "Use the filters to narrow the list to the requests you want to inspect.",
      "Open a request to read its input and output decisions, reason, and recorded details.",
      "Compare the decision with your workspace policy before deciding whether a rule needs adjusting.",
    ],
    tip: "A request stopped by the playground's client precheck never reaches the gateway, so it will not appear in these server logs.",
    action: { label: "Review policy settings", view: "policy" },
  },
  health: {
    title: "Check whether services are ready",
    description: "See whether the gateway and its supporting services are responding in this deployment.",
    steps: [
      "Refresh the checks to get the latest reported service status.",
      "Review unavailable dependencies or failed checks when requests cannot complete.",
      "Check provider circuit states to see whether a provider is currently accepting another request.",
    ],
    tip: "These checks describe the current deployment. A healthy service does not guarantee that a particular prompt or provider request will succeed.",
    action: { label: "Open setup and project guide", view: "about" },
  },
  keys: {
    title: "Connect your application",
    description: "Gateway API keys let your applications send requests with a specific set of permissions.",
    steps: [
      "Create a key with a name that identifies the application using it and the access it needs.",
      "Copy the complete key when it is shown. You cannot retrieve it again from the list.",
      "Review key usage and revoke a key when the application no longer needs access.",
    ],
    tip: "A grg_ key authenticates with this gateway. Your AI provider's key is different and stays in the server environment.",
    action: { label: "Read the connection guide", view: "about" },
  },
  policy: {
    title: "Choose how requests are handled",
    description: "Policies define the checks and limits your workspace applies to AI model requests.",
    steps: [
      "Review the input, output, sensitive-data, and traffic controls available for your workspace.",
      "If you are an administrator, adjust the controls for your use case and save your changes.",
      "Try representative prompts in the playground and inspect the decisions before relying on the policy.",
    ],
    tip: "Sensitive-data handling is configurable: it can block or redact supported data. The playground's separate client precheck can stop a prompt before server policy runs.",
    action: { label: "Test a prompt", view: "chat" },
  },
  teams: {
    title: "Choose your workspace",
    description: "Teams give people a shared workspace for model traffic, policies, and agent skills.",
    steps: [
      "Open a team you belong to, or create a team for a new workspace.",
      "Check which team is current before working with its policies, keys, and request records.",
      "Open team details to review members and the permissions available to your role.",
    ],
    tip: "Creating a team makes you an administrator of that workspace. Administrators manage its membership and settings.",
    action: { label: "View current team", view: "team" },
  },
  team: {
    title: "Understand team access",
    description: "See who belongs to the current workspace and manage membership according to your role.",
    steps: [
      "Review the current team and use the member filters to find a person.",
      "Administrators can invite people, add existing accounts, and update member access.",
      "Use All teams when you need to switch to another workspace.",
    ],
    tip: "An administrator can change other people's access. Last sign-in shows a recorded visit, not whether someone is online now.",
    action: { label: "Choose another team", view: "teams" },
  },
  billing: {
    title: "Understand tokens and credits",
    description: "Review your token balance, usage, and any credit purchases available in this deployment.",
    steps: [
      "Check your available balance and the total tokens used so far.",
      "If purchases are enabled, review the price and size of a credit pack before opening checkout.",
      "Use purchase history to inspect payment status, then refresh after a confirmed payment.",
    ],
    tip: "Tokens are units of text processed by an AI model. Billing is optional, so purchases or balance limits may be disabled in your deployment.",
    action: { label: "Explore usage analytics", view: "analytics" },
  },
  admin: {
    title: "Manage workspace access",
    description: "Administrators can review accounts, gateway keys, and temporary restrictions in the current workspace.",
    steps: [
      "Find an account and review its role, access, and recorded usage.",
      "Inspect the reason and retry time for a temporary restriction before lifting it.",
      "Review active gateway keys and revoke credentials that should no longer work.",
    ],
    tip: "Permission changes affect real workspace access. Check the selected account or key before applying an action.",
    action: { label: "Manage team membership", view: "team" },
  },
  settings: {
    title: "Make the workspace work for you",
    description: "Manage your account preferences and the workspace settings available to your role.",
    steps: [
      "Update your display name, appearance, or password in the relevant section.",
      "Administrators can manage workspace details, request limits, and notification settings.",
      "Save each section after making changes and check the confirmation message.",
    ],
    tip: "Available controls depend on your role and deployment. Model routing and some external connections are configured on the server in private deployments.",
    action: { label: "Review request policies", view: "policy" },
  },
  profile: {
    title: "Keep your profile up to date",
    description: "Review the identity and account details your teammates see in this workspace.",
    steps: [
      "Check your account role and email verification status on the profile card.",
      "Edit your display name and select Save profile.",
      "Open Settings to change your password or review other account preferences.",
    ],
    tip: "Your sign-in email is shown for reference and cannot be changed here. Workspace controls are available to administrators.",
    action: { label: "Open account settings", view: "settings" },
  },
  about: {
    title: "Get to know the project",
    description: "Learn what the gateway does, how a request moves through it, and where to start.",
    steps: [
      "Read the request flow to see how input checks, model calls, and output checks fit together.",
      "Follow a guide for setup, connecting an application, or scanning agent instructions.",
      "Use the common questions and project links when you need more detail.",
    ],
    tip: "LLM means large language model, a type of AI model. Guardrails add configurable checks around it; they can reduce risks but do not catch every problem.",
    action: { label: "Try the AI playground", view: "chat" },
  },
};
