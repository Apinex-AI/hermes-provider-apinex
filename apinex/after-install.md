# APInex providers installed

Set your key and pick a model:

    export APINEX_API_KEY="sk-apx-..."
    hermes --provider apinex --model claude-sonnet-5.5
    hermes --provider apinex-openai --model free/deepseek-v4.1-flash

`apinex` serves Claude models (`claude-sonnet-5.5`, `claude-opus-5.5`,
`claude-fable-5.1`, `free/claude-sonnet-4.6`, `free/claude-opus-4.6`) over the
native Anthropic Messages API (`https://api.apinex.bond/v1/messages`), so
Hermes' Anthropic prompt caching and thinking work natively. `apinex-openai`
serves GPT, Gemini, DeepSeek, GLM, Qwen, Kimi, Grok and Free-tier chat models
over the OpenAI-compatible API (`https://api.apinex.bond/v1`). Both use the
same `APINEX_API_KEY`. Or run `hermes model` and choose either provider.

Create an account and an API key at
<https://apinex.bond/register?utm_source=hermes&utm_medium=plugin>; the Hermes
setup guide is at
<https://apinex.bond/integrations/hermes?utm_source=hermes&utm_medium=plugin>
(по-русски: <https://apinex.bond/ru/integrations/hermes?utm_source=hermes&utm_medium=plugin>,
简体中文: <https://apinex.bond/zh/integrations/hermes?utm_source=hermes&utm_medium=plugin>).

Optional APInex HTTP tool skills (Web Search, Twitter/X Read API, Solana RPC,
Captcha Solver, Voice STT/TTS) can be installed with:

    hermes skills search https://apinex.bond --source well-known
