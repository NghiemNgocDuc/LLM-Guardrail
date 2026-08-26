# Org custom rule for the guardrails gateway (mirrors OPA's expected shape:
# decision object with action in {block, warn, pass} and a string reason).
package guardrails

import rego.v1

default decision := {"action": "pass", "reason": "no finding"}

decision := {"action": "block", "reason": "secret detected"} if {
	input.findings[i].matched
	input.findings[i].check == "Secret Detection"
}

allow contains prompt if {
	prompt := input.prompt
	not decision.action == "pass"
}
