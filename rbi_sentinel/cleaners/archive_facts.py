"""Deterministic archive metadata from stored Resolution text; no model calls."""
import re

from rbi_sentinel.cleaners.policy_facts import extract_policy_facts

STANCES = r"neutral|accommodative|withdrawal of accommodation|calibrated tightening"
COUNTS = {'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5, 'six': 6}


def stated_stance(text):
    flat = ' '.join((text or '').split())
    stance = extract_policy_facts(flat)['stated_stance']
    if stance:
        return stance
    # These older formulations describe the committee decision, not dissent.
    patterns = [
        rf'decision of the MPC is consistent with (?:an? |the )?({STANCES}) stance',
        rf'decision of the MPC is consistent with the stance of ({STANCES})',
        rf'MPC (?:also )?decided to maintain the ({STANCES}) monetary policy stance',
        rf'MPC decided to keep the policy stance ({STANCES})',
        rf'MPC (?:also )?decided to (?:change|maintain) (?:the )?stance (?:of monetary policy )?(?:to |as )?[‘\'"]?({STANCES})',
        rf'MPC (?:also )?decided to remain (accommodative while focusing on withdrawal of accommodation)',
        rf'MPC unanimously voted to reduce the policy repo rate and to maintain the (accommodative) stance',
    ]
    for pattern in patterns:
        match = re.search(pattern, flat, re.I)
        if match:
            return match[1].lower()
    return None


def rate_vote(text, action, bps):
    """Count support for the adopted rate decision, distinct from stance votes."""
    flat = ' '.join((text or '').split())
    flat = re.sub(r'\b(Dr|Prof)\.', r'\1', flat)
    flat = re.sub(r'\b([A-Z])\.', r'\1', flat)
    sentences = re.split(r'(?<!\d)\.(?!\d)', flat)
    supporting = []
    unanimous = False
    for sentence in sentences:
        if not re.search(r'vot|unanimously decided|in favour of the monetary policy decision', sentence, re.I):
            continue
        # Stance votes must never be substituted for rate votes.
        if re.search(r'stance', sentence, re.I) and not re.search(r'(?:repo|policy) rate', sentence, re.I):
            continue
        if re.search(r'(?:unanimously.{0,30}(?:voted|decided)|voted unanimously).{0,80}(?:repo|policy) rate', sentence, re.I):
            unanimous = True
        numbered = re.search(r'\b(one|two|three|four|five|six|[1-6]) members voting (.{0,100})', sentence, re.I)
        if numbered:
            amount = re.search(r'(\d+) (?:basis points|bps)', numbered[2], re.I)
            if amount and bps is not None and int(amount[1]) == abs(bps):
                supporting.append(COUNTS.get(numbered[1].lower()) or int(numbered[1]))
        if action == 'hold' and re.search(r'MPC.{0,50}unanimously.{0,50}(?:keep|unchanged)', sentence, re.I):
            unanimous = True
        if action == 'hold' and re.search(r'decision on keeping the policy rate unchanged was unanimous', sentence, re.I):
            unanimous = True
        clauses = re.finditer(
            r'(?P<subject>.*?)(?:voted|voting|were in favour)(?P<choice>.*?)(?=(?:\b(?:Dr|Shri|Professor|Prof)\b.{0,90}?(?:voted|voting))|$)',
            sentence, re.I,
        )
        for match in clauses:
            subject, choice = match['subject'], match['choice']
            if re.search(r'stance', choice, re.I) and not re.search(r'(?:repo|policy) rate', choice, re.I):
                continue
            count_match = re.search(r'\b(one|two|three|four|five|six|[1-6]) members', subject, re.I)
            count = (COUNTS.get(count_match[1].lower()) or int(count_match[1])) if count_match else len(re.findall(r'\b(?:Dr|Shri|Professor|Prof)\b', subject))
            if not count or count > 6:
                continue
            supports = bool(re.search(r'(?:in favour of (?:the (?:monetary policy )?decision|keeping)|of the monetary policy decision)', choice, re.I))
            if action == 'hold':
                supports |= bool(re.search(r'keep\w* .{0,35}(?:repo|policy) rate (?:unchanged|at)', choice, re.I))
            elif action in ('cut', 'hike'):
                direction = r'reduc\w*|decreas\w*|cut' if action == 'cut' else r'increas\w*|rais\w*|hike'
                amount = re.search(r'(\d+) (?:basis points|bps)', choice, re.I)
                supports |= bool(re.search(direction, choice, re.I) and amount and bps is not None and int(amount[1]) == abs(bps))
            if supports:
                supporting.append(count)
    count = max(supporting, default=0)
    if count:
        return f'{count}–{6 - count}'
    if unanimous:
        return '6–0'
    return None
