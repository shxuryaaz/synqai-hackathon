import os
os.environ["OPENAI_API_KEY"] = ""  # tests never call the network; the fake backend covers the cache path
