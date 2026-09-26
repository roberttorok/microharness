def probe_tools(tokenizer, tools):
    return tokenizer.apply_chat_template(
        [{"role": "user", "content": ""}], tools=tools,
        tokenize=False, add_generation_prompt=False)

