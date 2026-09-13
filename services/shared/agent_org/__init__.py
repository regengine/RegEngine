"""Agent organization: pods, agent identities, inboxes, suppression list.

See ``DESIGN_agent-org.md`` at the repo root for the full design. This
package is a real, minimal v1 of the underlying primitives behind
"an agent organization... N inboxes across M isolated pods, onboarded per
tenant in one function call" — it does not pre-seed any fixed pod/agent
count for any tenant, and its only inbox provider
(:class:`~shared.agent_org.providers.DevInboxProvider`) does not create a
real, internet-routable mailbox. See ``providers.py`` for that limitation
stated in full.
"""

from __future__ import annotations
