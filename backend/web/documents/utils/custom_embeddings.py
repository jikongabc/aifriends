import os

from langchain_core.embeddings import Embeddings
from openai import OpenAI


# 自定义 Embeddings：用阿里云 text-embedding-v4 接口替换默认实现。
class CustomEmbeddings(Embeddings):
    def __init__(self):
        self.client = OpenAI(
            api_key=os.getenv("API_KEY"), base_url=os.getenv("API_BASE")
        )

    # 分批（每批 10 条）向量化文档，过滤空串。
    def embed_documents(self, texts):
        batch_size = 10
        all_embeddings = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            batch = [t for t in batch if t.strip()]
            if not batch:
                continue
            response = self.client.embeddings.create(
                model="text-embedding-v4", input=batch, dimensions=1024
            )
            all_embeddings.extend([data.embedding for data in response.data])
        return all_embeddings

    # 向量化单条查询。
    def embed_query(self, text):
        return self.embed_documents([text])[0]
