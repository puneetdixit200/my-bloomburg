PROMPTS = {
    "STARTUP_GAP": """
You are an expert startup analyst.
Here are {count} user complaints about {topic} collected from Reddit,
App Store, Hacker News, and Product Hunt:

{complaints}

Analyze these complaints and:
1. Find the top 3 repeating pain patterns.
2. For each pattern, suggest one startup idea.
3. Rate each idea: market_size, competition_level, technical_difficulty, timing.
4. Pick the one idea you would build first and explain why.

Return ONLY valid JSON. No explanation outside JSON.
""".strip(),
    "TREND_VELOCITY": """
You are a technology trend analyst.
Here is velocity data for topic: {topic}

GitHub stars/week: {github_velocity}
Reddit mentions/week: {reddit_velocity}
HN appearances: {hn_count}
arXiv papers/month: {arxiv_velocity}
Job postings/month: {job_velocity}
Google Trends score: {trends_score}
Sources confirming: {source_count}

Analyze:
1. What phase is this trend in? emerging, accelerating, peaking, or declining.
2. Time to mainstream adoption, estimated in months.
3. Best time to learn this skill, build in this space, and invest.
4. Triggers that could accelerate or kill this trend.
5. Confidence level from 0 to 100.

Return ONLY valid JSON.
""".strip(),
    "DAILY_BRIEFING": """
You are an intelligence analyst writing a daily brief.
Today's signals:

TOP GITHUB REPOS: {github_signals}
TOP REDDIT TRENDS: {reddit_signals}
HN FRONT PAGE: {hn_signals}
RESEARCH PAPERS: {arxiv_signals}
FUNDING NEWS: {funding_signals}
HACKATHON ALERTS: {hackathon_signals}
JOB MARKET: {job_signals}

User profile: {user_profile}

Write a concise, actionable daily intelligence brief.
Format:
- What's exploding today
- Top opportunity for this user specifically
- One skill to learn now
- One startup gap spotted
- Recommended action today

Max 400 words. Direct. No fluff.
""".strip(),
    "SKILL_RADAR": """
Analyze job posting trends and GitHub/arXiv data:

Job postings mentioning these skills, including count change versus last month:
{skill_job_data}

GitHub repos using these technologies:
{github_tech_data}

arXiv papers on these topics:
{arxiv_tech_data}

Which 3 skills should someone learn RIGHT NOW?
Explain why using market timing, difficulty, and opportunity window.
Be specific about timeline, for example: this skill will peak in demand in about 6 months.

Return ONLY valid JSON.
""".strip(),
    "HACKATHON_ANALYSIS": """
Analyze this hackathon and predict the opportunity window:

Name: {name}
Prize: {prize}
Current participants: {participants}
Days left: {days_left}
Theme: {theme}
Sponsors: {sponsors}
Social mentions trend: {social_data}

Return JSON with:
1. opportunity_score from 0 to 100
2. crowd_prediction
3. what_to_build_to_win
4. relevant_skills

Return ONLY valid JSON.
""".strip(),
}
