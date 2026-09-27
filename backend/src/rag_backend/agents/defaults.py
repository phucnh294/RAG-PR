"""Seed input for the Agents tab.

DEFAULT_REGISTER_REQUIREMENT describes exactly what myweb/site/myweb/app.js implements:
edit both together. A rule stated here but missing from the page shows up as a failing
test the validation agent should classify as app_defect — which is also a useful way to
check that the pipeline catches real defects.
"""

from __future__ import annotations

DEFAULT_REGISTER_REQUIREMENT = """\
Feature: Register Account

The Register Account page lets a visitor create an account.

Fields:
- First name is required. It must be at most 50 characters.
- Last name is required. It must be at most 50 characters.
- Date of birth is optional. When entered, it must use the DD/MM/YYYY format and be a real \
calendar date.
- Date of birth cannot be in the future.
- Email is required and must be a valid email address (for example abc@gmail.com).

Validation messages (shown under the field when Register is clicked):
- "First name is required." / "Last name is required." / "Email is required."
- "First name must be at most 50 characters." / "Last name must be at most 50 characters."
- "Email must be a valid email address."
- "Date of birth must be in DD/MM/YYYY format."
- "Date of birth cannot be in the future."

Behaviour:
- When all fields are valid and Register is clicked, the page shows the message \
"Account <number> has been created successfully!" and clears the form. The first account \
created in a new browser session is number 123.
- When any field is invalid, no account is created and no success message is shown.
- Clicking Back clears the form, removes all validation messages and hides the success \
message.
"""
