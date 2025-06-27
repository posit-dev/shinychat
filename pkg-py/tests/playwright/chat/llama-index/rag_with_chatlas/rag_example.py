import os

from chatlas import ChatOpenAI
from llama_index.core import StorageContext, load_index_from_storage

_ = os.environ.get("OPENAI_API_KEY")


# Load the knowledge store (index) from disk
try:
    storage_context = StorageContext.from_defaults(persist_dir="./storage")
    index = load_index_from_storage(storage_context)
    print("LlamaIndex loaded successfully from ./storage")
except Exception as e:
    print(f"Error loading LlamaIndex: {e}")
    print(
        "Please ensure you have run the index creation script first if this is your initial run."
    )
    from llama_index.core import Document, VectorStoreIndex

    print("Creating a dummy index for demonstration purposes...")
    bookstore_documents = [
        "Our shipping policy states that standard shipping takes 3-5 business days. Express shipping takes 1-2 business days. Free shipping is offered on all orders over $50.",
        "Returns are accepted within 30 days of purchase, provided the book is in its original condition. To initiate a return, please visit our 'Returns' page on the website and fill out the form.",
        "The 'BookWorm Rewards' program offers members 10% off all purchases and early access to sales. You earn 1 point for every $1 spent.",
        "We accept Visa, Mastercard, American Express, and PayPal.",
        "Currently, we do not offer international shipping outside of the United States and Canada.",
        "The book 'The Midnight Library' by Matt Haig is a New York Times bestseller. It explores themes of regret and parallel lives.",
        "Orders placed before 2 PM EST are processed on the same day.",
    ]
    documents = [Document(text=d) for d in bookstore_documents]
    index = VectorStoreIndex.from_documents(documents)
    index.storage_context.persist(persist_dir="./storage")
    print("Dummy index created and saved.")


def retrieve_trusted_content(
    query: str, top_k: int = 3
):
    """
    Retrieve relevant content from the bookstore's knowledge base.
    This acts as the "lookup" for our customer service assistant.

    Parameters
    ----------
    query
        The customer's question used to semantically search the knowledge store.
    top_k
        The number of most relevant policy/book excerpts to retrieve.
    """
    retriever = index.as_retriever(similarity_top_k=top_k)
    nodes = retriever.retrieve(query)
    # Format the retrieved content clearly so Chatlas can use it as "trusted" information
    return [f"<excerpt>{x.text}</excerpt>" for x in nodes]


chat = ChatOpenAI(
    system_prompt=(
        "You are 'BookWorm Haven's Customer Service Assistant'. "
        "Your primary goal is to help customers with their queries about shipping, returns, "
        "payment methods, and book information based *only* on the provided trusted content. "
        "If you cannot answer the question using the trusted content, politely state that "
        "you don't have that information and suggest they visit the 'Help' section of the website."
    ),
    model="gpt-4o-mini",
)

# This is where Chatlas learns to "look up" information when needed.
chat.register_tool(retrieve_trusted_content)


# Example Customer Interactions with the Assistant
print("\n--- BookWorm Haven Customer Service ---\n")

# Example 1: Question that can be answered from the knowledge base (shipping policy)
customer_query_1 = "How long does standard shipping take?"
print(f"Customer: {customer_query_1}")
response_1 = chat.chat(customer_query_1)
print(f"Assistant: {response_1}\n")

# Example 2: Another question answerable from the knowledge base (return policy)
customer_query_2 = "What's your return policy?"
print(f"Customer: {customer_query_2}")
response_2 = chat.chat(customer_query_2)
print(f"Assistant: {response_2}\n")

# Example 3: Question about a specific book (information available)
customer_query_3 = "Tell me about 'The Midnight Library'."
print(f"Customer: {customer_query_3}")
response_3 = chat.chat(customer_query_3)
print(f"Assistant: {response_3}\n")

# Example 4: Question with information not in the knowledge base
customer_query_4 = "Do you have any books about quantum physics for beginners?"
print(f"Customer: {customer_query_4}")
response_4 = chat.chat(customer_query_4)
print(f"Assistant: {response_4}\n")

# Example 5: Combining information
customer_query_5 = "Is free shipping available and what payment methods do you accept?"
print(f"Customer: {customer_query_5}")
response_5 = chat.chat(customer_query_5)
print(f"Assistant: {response_5}\n")

# Example 6: More nuanced query requiring retrieval
customer_query_6 = "I want to return a book, what should I do?"
print(f"Customer: {customer_query_6}")
response_6 = chat.chat(customer_query_6)
print(f"Assistant: {response_6}\n")
