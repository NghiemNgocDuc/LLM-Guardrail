"""Ordinary tutorials and typed auth references retain all other output checks."""
import pytest

from app.defaults import DEFAULT_COMPLIANCE, DEFAULT_OUTPUT_RULES, DEFAULT_TOPIC_POLICY
from guardrails.output import OutputGuardrail


def guardrail():
    return OutputGuardrail(DEFAULT_OUTPUT_RULES, DEFAULT_COMPLIANCE, DEFAULT_TOPIC_POLICY)


@pytest.mark.parametrize("response", [
    "Follow these steps to commit your changes to Git: stage the files, then create a commit.",
    "Here are the instructions for mass importing public CSV rows.",
    "The instructions for mass spectrometry describe sample preparation.",
    "Set the header Authorization: Bearer <your_token> when connecting to the gateway.",
    "Set Authorization: Bearer ${ACCESS_TOKEN} from the environment.",
    'curl -H "Authorization: Bearer ${ACCESS_TOKEN}" https://gateway.example/chat',
])
def test_benign_tutorials_and_auth_reference_templates_are_allowed(response):
    assert guardrail().check(response).allowed


@pytest.mark.parametrize("response", [
    "Follow these steps to commit murder.",
    "Follow these steps to commit suicide.",
    "Here are the instructions for mass shooting.",
    "Here are the instructions for mass killing.",
    "Follow these steps to commit your changes to Git. Then follow these steps to commit arson.",
])
def test_complete_harmful_instructions_still_block(response):
    result = guardrail().check(response)
    assert not result.allowed and result.reason_code == "toxic_content"


@pytest.mark.parametrize("response", [
    "Authorization: Bearer secret-token",
    "Authorization: Bearer <actual_private_value>",
    "Authorization: Bearer ${ACCESS_TOKEN:-synthetic_private_credential}",
    "Authorization: Bearer <your_token>\nAuthorization: Bearer secret-token",
    "Authorization: Bearer ${ACCESS_TOKEN}\nGateway key: " + "grg_" + "A" * 40,
    "api_key=synthetic_private_credential",
])
def test_templates_cannot_hide_literal_credentials(response):
    result = guardrail().check(response)
    assert not result.allowed and result.reason_code == "secret_leakage"


def test_explicit_topic_policy_still_applies_to_benign_tutorials():
    result = OutputGuardrail(DEFAULT_OUTPUT_RULES, {}, {"blocked_topics": ["Git"]}).check(
        "Follow these steps to commit your changes to Git."
    )
    assert not result.allowed and result.reason_code == "blocked_topic"


@pytest.mark.parametrize("response", [
    "You should take 20 mg of this prescription medicine twice daily.",
    "I diagnose you with an infection and recommend a prescription dosage.",
])
def test_medical_advice_policy_remains_active(response):
    result = guardrail().check(response)
    assert not result.allowed and result.reason_code == "blocked_topic"
