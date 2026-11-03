import { ai, router, json, error } from '@appdeploy/sdk';

type ChatBody = {
  message?: unknown;
  language?: unknown;
  simpleLanguage?: unknown;
  history?: unknown;
};

const schema = {
  type: 'object',
  additionalProperties: false,
  properties: {
    reply: { type: 'string' },
    plan: {
      type: 'object',
      additionalProperties: false,
      properties: {
        title: { type: 'string' },
        description: { type: 'string' },
        steps: {
          type: 'array',
          minItems: 3,
          maxItems: 7,
          items: {
            type: 'object',
            additionalProperties: false,
            properties: {
              title: { type: 'string' },
              detail: { type: 'string' },
            },
            required: ['title', 'detail'],
          },
        },
      },
      required: ['title', 'description', 'steps'],
    },
  },
  required: ['reply'],
};

const system = [
  'You are LIFEKEY AI, an accessible practical problem-solving assistant and learning companion.',
  'Understand the outcome the user wants, explain complicated information in plain language, and help them take realistic next steps.',
  'Support coding in Python, JavaScript, HTML and CSS. Explain code for beginners, identify likely bugs, show corrected examples, explain errors and suggest simple tests. Never claim to have run code unless it was actually executed.',
  'When given a problem statement, identify the core problem, affected people, context, likely causes, evidence to collect, scope, desired outcome and measurable success criteria. Separate facts from assumptions.',
  'When reviewing document text, provide a plain-language summary, purpose, strengths, unclear or missing information, risks or questions to verify, specific improvements and prioritised next steps. Invite follow-up questions and explain what the user is getting.',
  'Respect the selected language and simple-language preference.',
  'When an action plan is appropriate and there is enough information, create 3 to 7 small, ordered steps. Make them specific, realistic and achievable with the resources the user described. Explain what to do, why it matters and what result to expect.',
  'If essential information is missing, ask one useful clarifying question instead of inventing details. Do not force an action plan when a clarification is needed.',
  'Be specific, supportive, concise and useful. Avoid generic chatbot filler.',
  'Never invent official requirements, deadlines, job vacancies, prices, legal rules or medical facts.',
  'Do not claim to open apps, access the user’s computer or local files, send messages, make payments or change computer settings.',
  'Never pretend an external action, reminder, payment or device operation has been completed.',
  'Do not ask for sensitive personal information unless essential.',
  'Return a JSON object matching the supplied schema.',
].join(' ');

export const handler = router({
  'GET /api/health': [
    async () =>
      json({ status: 'ok', service: 'LIFEKEY AI', aiConfigured: true }),
  ],
  'POST /api/chat': [
    async ({ body }) => {
      const request = (body || {}) as ChatBody;
      const message =
        typeof request.message === 'string' ? request.message.trim() : '';

      if (!message) {
        return error('Please enter a message before sending.', 400);
      }

      if (message.length > 6000) {
        return error('Please keep your message under 6,000 characters.', 413);
      }

      const language =
        typeof request.language === 'string'
          ? request.language.slice(0, 80)
          : 'English (South Africa)';

      const simple = request.simpleLanguage !== false;

      const history = Array.isArray(request.history)
        ? request.history
            .slice(-8)
            .map(item => {
              const entry = item as { role?: unknown; content?: unknown };
              const speaker = entry.role === 'assistant' ? 'LIFEKEY' : 'USER';

              const content =
                typeof entry.content === 'string'
                  ? entry.content.slice(0, 1000)
                  : '';

              return content ? speaker + ': ' + content : '';
            })
            .filter(Boolean)
            .join('\n')
        : '';

      const prompt = [
        'Preferred language: ' + language + '.',
        'Use simple language: ' + (simple ? 'yes' : 'no') + '.',
        history ? 'Recent conversation context:\n' + history : '',
        'Current request:\n' + message,
        'Give an answer the user can act on. State uncertainty where appropriate. Make the action plan relevant to this request. Explain what each action is for, why it matters and what result to expect.',
      ]
        .filter(Boolean)
        .join('\n\n');

      try {
        const result = await ai.generate({
          system,
          prompt,
          schema,
          maxTokens: 1500,
          temperature: 0.35,
          thinkingMode: 'FAST',
        });

        const parsed = JSON.parse(result.text) as {
          reply?: string;
          plan?: {
            title?: string;
            description?: string;
            steps?: { title?: string; detail?: string }[];
          };
        };

        const steps = Array.isArray(parsed.plan?.steps)
          ? parsed.plan.steps.slice(0, 7).map(step => ({
              title: String(step.title || 'Next step').slice(0, 120),
              detail: String(step.detail || '').slice(0, 500),
            }))
          : [];

        const plan =
          parsed.plan && steps.length >= 3
            ? {
                title: String(parsed.plan.title || 'Your next steps').slice(
                  0,
                  120
                ),
                description: String(
                  parsed.plan.description || 'A practical plan based on your request.'
                ).slice(0, 500),
                steps,
              }
            : undefined;

        return json({
          reply: String(parsed.reply || result.text).slice(0, 9000),
          ...(plan ? { plan } : {}),
        });
      } catch (cause) {
        console.error('LIFEKEY AI generation failed', cause);

        return error(
          'LIFEKEY could not generate a response right now. Please try again in a moment.',
          502
        );
      }
    },
  ],
});