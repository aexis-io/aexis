from google import genai

from aexis import core
from pydantic import BaseModel

def main():
    client = genai.Client()
    response = client.models.generate_content(
        model=core.model, contents="Explain how AI works in a few words"
    )
    print(response.text)


if __name__ == "__main__":
    main()
