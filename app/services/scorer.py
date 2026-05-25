import anthropic
import json
import os
from dotenv import load_dotenv

load_dotenv()

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

AXIS_DEFINITIONS = """
1. joy: Happiness, warmth, positivity, celebration (0=none, 1=intense joy)
2. trust: Reassurance, credibility, safety, reliability (0=none, 1=strong trust)
3. anticipation: Excitement, curiosity, looking forward to something (0=none, 1=intense anticipation)
4. surprise: Novelty, unexpected, pattern-interrupt (0=none, 1=shocking surprise)
5. fear: Anxiety, loss aversion, worry, risk (0=none, 1=intense fear)
6. urgency: Scarcity, time pressure, FOMO, act now (0=none, 1=extreme urgency)
7. nostalgia: Longing for the past, heritage, memories (0=none, 1=deep nostalgia)
8. aspiration: Pride, status, self-improvement, ambition (0=none, 1=strong aspiration)
9. belonging: Community, togetherness, social connection, love (0=none, 1=strong belonging)
10. sadness: Empathy, melancholy, emotional depth (0=none, 1=intense sadness)
"""

FEW_SHOT_EXAMPLES = """
EXAMPLE 1 - Hard-sell DR creative (English):
Text: "LAST CHANCE! 70% OFF ends tonight. Don't miss out - over 500 sold!"
Scores: joy=0.3, trust=0.2, anticipation=0.4, surprise=0.3, fear=0.5, urgency=0.95, nostalgia=0.0, aspiration=0.3, belonging=0.1, sadness=0.0

EXAMPLE 2 - Heritage brand creative (Latvian):
Text: "Jau 30 gadus mēs nesam Latvijas tradīcijas jūsu ģimenei. Ziemassvētki ir mājās."
(Translation: For 30 years we have brought Latvian traditions to your family. Christmas is at home.)
Scores: joy=0.7, trust=0.8, anticipation=0.3, surprise=0.0, fear=0.0, urgency=0.1, nostalgia=0.9, aspiration=0.2, belonging=0.85, sadness=0.1

EXAMPLE 3 - Cause marketing creative (Latvian):
Text: "Katrs bērns Latvijā ir pelnījis nākotni. Palīdzi mums to nodrošināt."
(Translation: Every child in Latvia deserves a future. Help us ensure it.)
Scores: joy=0.2, trust=0.6, anticipation=0.3, surprise=0.0, fear=0.3, urgency=0.4, nostalgia=0.1, aspiration=0.5, belonging=0.7, sadness=0.65
"""

SCORING_TOOL = {
    "name": "score_emotions",
    "description": "Score the emotional dimensions of ad creative or cultural context",
    "input_schema": {
        "type": "object",
        "properties": {
            "joy": {"type": "number", "minimum": 0, "maximum": 1},
            "trust": {"type": "number", "minimum": 0, "maximum": 1},
            "anticipation": {"type": "number", "minimum": 0, "maximum": 1},
            "surprise": {"type": "number", "minimum": 0, "maximum": 1},
            "fear": {"type": "number", "minimum": 0, "maximum": 1},
            "urgency": {"type": "number", "minimum": 0, "maximum": 1},
            "nostalgia": {"type": "number", "minimum": 0, "maximum": 1},
            "aspiration": {"type": "number", "minimum": 0, "maximum": 1},
            "belonging": {"type": "number", "minimum": 0, "maximum": 1},
            "sadness": {"type": "number", "minimum": 0, "maximum": 1},
            "rationale": {"type": "string", "description": "One sentence explaining the top 2-3 scoring axes"}
        },
        "required": ["joy","trust","anticipation","surprise","fear","urgency","nostalgia","aspiration","belonging","sadness","rationale"]
    }
}

def score_text(text: str) -> dict:
    """Score a single text. Returns one score dict."""
    message = client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=500,
        temperature=0,
        tools=[SCORING_TOOL],
        tool_choice={"type": "tool", "name": "score_emotions"},
        messages=[{
            "role": "user",
            "content": f"""You are an expert in emotional analysis of advertising and cultural context.

Score the following text on 10 emotional axes using the score_emotions tool.

AXIS DEFINITIONS:
{AXIS_DEFINITIONS}

CALIBRATION EXAMPLES:
{FEW_SHOT_EXAMPLES}

TEXT TO SCORE:
{text}

Use the score_emotions tool to return your scores."""
        }]
    )
    for block in message.content:
        if block.type == "tool_use" and block.name == "score_emotions":
            return block.input
    raise ValueError("No tool use block returned from Claude")

def score_with_average(text: str, runs: int = 3) -> dict:
    """Run scoring N times and average. Used for creatives (cached after)."""
    results = [score_text(text) for _ in range(runs)]
    axes = ["joy","trust","anticipation","surprise","fear","urgency","nostalgia","aspiration","belonging","sadness"]
    averaged = {axis: round(sum(r[axis] for r in results) / runs, 3) for axis in axes}
    averaged["rationale"] = results[0]["rationale"]
    averaged["runs"] = runs
    return averaged

def scores_to_vector(scores: dict) -> list:
    """Convert score dict to ordered list for pgvector storage."""
    axes = ["joy","trust","anticipation","surprise","fear","urgency","nostalgia","aspiration","belonging","sadness"]
    return [scores[axis] for axis in axes]


def score_image(image_base64: str, media_type: str, caption_text: str = "") -> dict:
    """
    Score an ad creative from its IMAGE using Claude Vision.
    Analyzes visual emotional content + any provided caption/copy.
    """
    content = [
        {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": media_type,
                "data": image_base64
            }
        },
        {
            "type": "text",
            "text": f"""You are an expert in emotional analysis of advertising.

Analyze this ad creative IMAGE and score its emotional content on 10 axes using the score_emotions tool.
Consider the visual elements: colors, composition, facial expressions, setting, mood, lighting, and any text in the image.

{f'Caption/copy accompanying the ad: {caption_text}' if caption_text else ''}

AXIS DEFINITIONS:
{AXIS_DEFINITIONS}

CALIBRATION EXAMPLES:
{FEW_SHOT_EXAMPLES}

Use the score_emotions tool to return scores based on what you SEE in the image."""
        }
    ]

    message = client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=500,
        temperature=0,
        tools=[SCORING_TOOL],
        tool_choice={"type": "tool", "name": "score_emotions"},
        messages=[{"role": "user", "content": content}]
    )
    for block in message.content:
        if block.type == "tool_use" and block.name == "score_emotions":
            return block.input
    raise ValueError("No tool use block returned from Claude")
