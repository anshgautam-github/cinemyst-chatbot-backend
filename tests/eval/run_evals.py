import asyncio
import json
import os
import sys
import uuid
from pathlib import Path

# Add project root to path so we can import app
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.dependencies import get_chat_agent
from tests.eval.judge import LLMJudge


def load_dataset() -> list[dict]:
    dataset_path = Path(__file__).parent / "dataset.json"
    with open(dataset_path, "r", encoding="utf-8") as f:
        return json.load(f)


def print_separator():
    print("=" * 80)


async def main():
    print_separator()
    print("🚀 Starting CineMyst Evaluation Pipeline (LLM-as-Judge)")
    print_separator()
    
    dataset = load_dataset()
    agent = get_chat_agent()
    judge = LLMJudge()
    
    # We use a test user ID so we don't pollute real user histories
    test_user_id = f"test-eval-user-{uuid.uuid4().hex[:8]}"
    
    total_score = 0
    max_possible_score = len(dataset) * 10
    total_criteria_passed = 0
    total_criteria = 0
    
    results = []

    for i, test_case in enumerate(dataset, 1):
        test_id = test_case["id"]
        user_input = test_case["input"]
        expected_criteria = test_case["expected_criteria"]
        
        print(f"\n▶️  Running Test {i}/{len(dataset)}: {test_id}")
        print(f"   Input: '{user_input}'")
        
        # 1. Run the Agent (using a unique conversation ID for each test)
        conversation_id = f"eval-{test_id}-{uuid.uuid4().hex[:4]}"
        
        # In a real async environment, we might need to wrap sync calls or ensure we're inside the loop properly.
        # chat() is sync right now in the agent, but depends on async context sometimes. 
        # Actually, chat() is a sync function in agent.py
        
        try:
            answer, _ = agent.chat(user_id=test_user_id, message=user_input, conversation_id=conversation_id)
        except Exception as e:
            answer = f"AGENT CRASHED: {str(e)}"
            
        print(f"   Agent Answer: '{answer[:100]}...'")
        
        # 2. Run the Judge
        print(f"   ⚖️  Judging response...")
        try:
            eval_result = judge.evaluate(user_input, answer, expected_criteria)
            
            # Record scores
            total_score += eval_result.score
            
            passed_count = sum(1 for c in eval_result.criteria_evaluations if c.passed)
            total_criteria_passed += passed_count
            total_criteria += len(expected_criteria)
            
            print(f"   ✅ Score: {eval_result.score}/10")
            print(f"   Criteria Met: {passed_count}/{len(expected_criteria)}")
            for criteria in eval_result.criteria_evaluations:
                icon = "🟢" if criteria.passed else "🔴"
                print(f"      {icon} {criteria.reasoning}")
                
            results.append({
                "id": test_id,
                "score": eval_result.score,
                "passed": passed_count == len(expected_criteria)
            })
            
        except Exception as e:
            print(f"   ❌ Judge failed: {str(e)}")
            
    # Print Final Report
    print_separator()
    print("📊 EVALUATION REPORT")
    print_separator()
    
    for r in results:
        status = "PASSED" if r["passed"] else "FAILED"
        print(f"- {r['id']}: {r['score']}/10 ({status})")
        
    print_separator()
    percentage = (total_score / max_possible_score) * 100 if max_possible_score > 0 else 0
    crit_percentage = (total_criteria_passed / total_criteria) * 100 if total_criteria > 0 else 0
    
    print(f"Overall Quality Score: {total_score}/{max_possible_score} ({percentage:.1f}%)")
    print(f"Criteria Adherence:    {total_criteria_passed}/{total_criteria} ({crit_percentage:.1f}%)")
    print_separator()

if __name__ == "__main__":
    # Ensure environment variables are loaded if using python-dotenv
    # (FastAPI handles it automatically, but standalone script might need it)
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass
        
    asyncio.run(main())
