import json
import re
import time

from openai import OpenAI
from zappa.asynchronous import task

from brscans.manhwa.models import Manhwa

client = OpenAI(
    api_key="sk-f9a18faeb596425886f17afac4325c38",
    base_url="https://ds2api-blond.vercel.app/v1",
)

MODEL = "deepseek-chat"


def _translate_with_retry(title: str, description: str, max_retries=12):
    prompt = [
        {
            "role": "user",
            "content": (
                "Traduza o título e a descrição a seguir para português brasileiro "
                "de forma natural e fluida. Retorne APENAS um JSON no formato:\n"
                '{"title": "título traduzido", "description": "descrição traduzida"}\n\n'
                f"Título: {title}\n\n"
                f"Descrição: {description}"
            ),
        }
    ]

    response = None
    message = None

    for attempt in range(max_retries):
        try:
            response = client.chat.completions.create(
                model=MODEL,
                messages=prompt,
                stream=False,
                response_format={"type": "json_object"},
            )
            message = response.choices[0].message
            content = message.content or ""

            match = re.search(r"\{[\s\S]*\}", content)
            if match:
                data = json.loads(match.group(0))
                if "title" in data and "description" in data:
                    return data
        except json.JSONDecodeError:
            print(f"Attempt {attempt + 1}: Failed to decode JSON from content.")
        except Exception as e:
            print(f"Attempt {attempt + 1} failed with error:", e)

        if attempt < max_retries - 1:
            print(
                f"Retrying translation (Attempt {attempt + 2}/{max_retries})..."
            )
            time.sleep(1)

    return None


@task
def translate_manhwa(manhwa_id: int):
    manhwa = Manhwa.objects.filter(id=manhwa_id).first()
    if not manhwa:
        print(f"Manhwa {manhwa_id} not found")
        return True

    if manhwa.original_title:
        print(f"Manhwa {manhwa_id} already translated, skipping")
        return True

    original_title = manhwa.title
    original_description = manhwa.description or ""

    result = _translate_with_retry(original_title, original_description)

    if result is None:
        print(f"Failed to translate manhwa {manhwa_id} after retries")
        return True

    manhwa.original_title = original_title
    manhwa.original_description = original_description
    manhwa.title = result["title"]
    manhwa.description = result["description"]
    manhwa.save()

    print(
        f"Manhwa {manhwa_id} translated: '{original_title}' -> '{manhwa.title}'"
    )

    return True
