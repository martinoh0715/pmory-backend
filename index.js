const https = require('https');

// PMory Knowledge Base (RAG Data)
const pmoryKnowledge = {
  pmBasics: {
    definition: "Product Management is the practice of strategically driving the development, market launch, and continual support and improvement of a company's products.",
    responsibilities: ["Strategic Planning", "Market Research", "Feature Prioritization", "Cross-functional Collaboration", "Data Analysis", "User Advocacy"],
    skills: ["Analytical thinking", "Communication", "Leadership", "Technical understanding", "User empathy", "Business acumen"]
  },
  emoryAdvantages: [
    "Strong business foundation from Goizueta Business School",
    "Analytical thinking from rigorous coursework",
    "Leadership experience from various programs", 
    "Network of successful alumni in tech industry",
    "Case study methodology similar to PM problem-solving"
  ]
};

// Search knowledge base (RAG function)
function searchKnowledge(query) {
  const results = [];
  const queryLower = query.toLowerCase();
  const queryWords = queryLower.split(' ');
  
  Object.entries(pmoryKnowledge).forEach(([category, data]) => {
    if (typeof data === 'object' && !Array.isArray(data)) {
      Object.entries(data).forEach(([key, value]) => {
        if (typeof value === 'string') {
          if (queryWords.some(word => value.toLowerCase().includes(word))) {
            results.push(`${category}.${key}: ${value}`);
          }
        } else if (Array.isArray(value)) {
          value.forEach(item => {
            if (queryWords.some(word => item.toLowerCase().includes(word))) {
              results.push(`${category}.${key}: ${item}`);
            }
          });
        }
      });
    } else if (Array.isArray(data)) {
      data.forEach(item => {
        if (queryWords.some(word => item.toLowerCase().includes(word))) {
          results.push(`${category}: ${item}`);
        }
      });
    }
  });
  
  return results.slice(0, 3);
}

// Call Claude API with correct model name
async function callClaude(message, knowledgeContext) {
  const apiKey = process.env.ANTHROPIC_API_KEY;
  
  console.log('API Key present:', apiKey ? 'Yes' : 'No');
  
  if (!apiKey) {
    throw new Error('Anthropic API key not configured');
  }
  
  const systemPrompt = `You are a helpful AI assistant for PMory, specializing in Product Management guidance for Emory University students.

PMory Knowledge Base Context:
${knowledgeContext}

Use the provided knowledge base context when relevant, and supplement with your general knowledge. Always be encouraging and specific in your advice for Emory students.`;

  const requestData = JSON.stringify({
    model: 'claude-sonnet-4-20250514',
    max_tokens: 800,
    system: systemPrompt,
    messages: [
      {
        role: 'user',
        content: message
      }
    ]
  });

  return new Promise((resolve, reject) => {
    const options = {
      hostname: 'api.anthropic.com',
      port: 443,
      path: '/v1/messages',
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'x-api-key': apiKey,
        'anthropic-version': '2023-06-01'
      }
    };

    const req = https.request(options, (res) => {
      let data = '';
      
      res.on('data', (chunk) => {
        data += chunk;
      });
      
      res.on('end', () => {
        try {
          const response = JSON.parse(data);
          resolve(response);
        } catch (error) {
          reject(new Error(`Failed to parse Claude response: ${data}`));
        }
      });
    });

    req.on('error', (error) => {
      reject(error);
    });

    req.write(requestData);
    req.end();
  });
}

exports.handler = async (event) => {
  // Enhanced CORS headers for Lambda Function URLs
  const corsHeaders = {
    'Content-Type': 'application/json',
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Headers': 'Content-Type, Authorization, X-Requested-With',
    'Access-Control-Allow-Methods': 'GET, POST, OPTIONS, PUT, DELETE',
    'Access-Control-Max-Age': '86400'
  };

  // Handle ALL requests with CORS headers
  if (event.requestContext && event.requestContext.http && event.requestContext.http.method === 'OPTIONS') {
    return {
      statusCode: 200,
      headers: corsHeaders,
      body: JSON.stringify({ message: 'CORS preflight OK' })
    };
  }

  const response = {
    statusCode: 200,
    headers: corsHeaders
  };

  try {
    // Handle both Lambda Function URL and API Gateway event formats
    const httpMethod = event.requestContext?.http?.method || event.httpMethod || 'GET';
    const rawPath = event.requestContext?.http?.path || event.path || '/';
    const cleanPath = rawPath.replace(/^\/+/, '');

    if (cleanPath === '' && httpMethod === 'GET') {
      response.body = JSON.stringify({
        message: 'PMory AI - Real Claude Sonnet 4 Ready!',
        model: 'claude-sonnet-4-20250514',
        endpoints: {
          health: '/health',
          chat: '/api/chat (POST)'
        }
      });
    } 
    else if (cleanPath === 'health' && httpMethod === 'GET') {
      response.body = JSON.stringify({
        status: 'OK', 
        message: 'Claude Sonnet 4 connection ready',
        model: 'claude-sonnet-4-20250514'
      });
    }
    else if (cleanPath === 'api/chat' && httpMethod === 'POST') {
      const body = event.body ? JSON.parse(event.body) : {};
      const message = body.message || '';

      if (!message.trim()) {
        response.statusCode = 400;
        response.body = JSON.stringify({ error: 'Message is required' });
        return response;
      }

      console.log('Processing message with Claude Sonnet 4:', message);
      
      // Step 1: Search knowledge base (RAG)
      const knowledgeResults = searchKnowledge(message);
      const knowledgeContext = knowledgeResults.length > 0 
        ? knowledgeResults.join('\n') 
        : 'No specific PMory knowledge found for this query.';

      console.log('Knowledge results:', knowledgeResults);
      
      // Step 2: Call Claude Sonnet 4
      const claudeResponse = await callClaude(message, knowledgeContext);
      
      if (claudeResponse.content && claudeResponse.content[0]) {
        response.body = JSON.stringify({ 
          response: claudeResponse.content[0].text,
          knowledge_used: knowledgeResults.length > 0,
          rag_results: knowledgeResults,
          ai_model: 'Claude Sonnet 4',
          system: 'Real AI with RAG'
        });
      } else {
        throw new Error(`Invalid Claude response structure: ${JSON.stringify(claudeResponse)}`);
      }
    }
    else {
      response.statusCode = 404;
      response.body = JSON.stringify({ error: 'Not found' });
    }

  } catch (error) {
    console.error('Error in handler:', error);
    response.statusCode = 500;
    response.body = JSON.stringify({ 
      error: 'Internal server error', 
      details: error.message
    });
  }

  return response;
};
