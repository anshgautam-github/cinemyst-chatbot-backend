import json
from typing import List

from langchain_core.prompts import ChatPromptTemplate
from langchain_groq import ChatGroq
from pydantic import BaseModel, Field

from app.config import get_settings


class CriteriaEvaluation(BaseModel):
    criteria: str = Field(description="The exact criteria being evaluated")
    passed: bool = Field(description="Whether the response met the criteria")
    reasoning: str = Field(description="Why it passed or failed")


class EvaluationResult(BaseModel):
    score: int = Field(description="Score from 0 to 10 based on overall quality and criteria met")
    criteria_evaluations: List[CriteriaEvaluation] = Field(
        description="Evaluation of each specific expected criteria"
    )
    overall_feedback: str = Field(description="General feedback on the response quality")


JUDGE_PROMPT = """You are an expert AI evaluator judging a conversational assistant for a film industry platform called CineMyst.
Your job is to evaluate the assistant's response to a user's input based on a strict set of expected criteria.

USER INPUT:
{input}

ASSISTANT RESPONSE:
{response}

EXPECTED CRITERIA:
{criteria}

Evaluate the response carefully. For each expected criteria, determine if the assistant met the requirement.
Then, provide an overall score from 0 to 10 (10 being perfect adherence to criteria and excellent tone, 0 being a complete failure or harmful response).
Provide your final output in the requested JSON format.
"""


class LLMJudge:
    def __init__(self):
        settings = get_settings()
        # We use a capable model for the judge
        self.llm = ChatGroq(
            api_key=settings.groq_api_key,
            model_name=settings.groq_model,
            temperature=0.0,
        )
        self.structured_llm = self.llm.with_structured_output(EvaluationResult)
        self.prompt = ChatPromptTemplate.from_template(JUDGE_PROMPT)

    def evaluate(self, user_input: str, response: str, expected_criteria: list[str]) -> EvaluationResult:
        """Run the LLM-as-judge to evaluate a single response."""
        criteria_str = "\n".join([f"- {c}" for c in expected_criteria])
        
        chain = self.prompt | self.structured_llm
        
        result = chain.invoke({
            "input": user_input,
            "response": response,
            "criteria": criteria_str
        })
        
        return result
