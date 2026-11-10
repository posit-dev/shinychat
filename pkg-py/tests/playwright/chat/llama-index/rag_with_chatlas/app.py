
from chatlas import ChatOpenAI
from dotenv import load_dotenv
from llama_index.core import StorageContext, load_index_from_storage
from shiny.express import ui

_ = load_dotenv()


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


def retrieve_trusted_content(query: str, top_k: int = 3):
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


chat_client = ChatOpenAI(
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
chat_client.register_tool(retrieve_trusted_content)


ui.page_opts(
    title="BookWorm Haven Customer Service",
    fillable=True,
    fillable_mobile=True,
)

chat = ui.Chat(
    id="chat",
    messages=[
        """
Hello! I am BookWorm Haven's Customer Service Assistant.

Here are some examples of what you can ask me:

- <span class="suggestion"> How long does standard shipping take? </span>
- <span class="suggestion"> What is your return policy? </span>
- <span class="suggestion"> Can you tell me about 'The Midnight Library'? </span>

        """
    ],
)
chat.ui()


# Generate a response when the user submits a message
@chat.on_user_submit
async def handle_user_input(user_input: str):
    response = await chat_client.stream_async(user_input)
    await chat.append_message_stream(response)
