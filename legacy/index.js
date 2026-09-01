const https = require('https');

// PMory Knowledge Base (RAG Data) - EXPANDED VERSION
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
  ],
  // ADD THIS NEW SECTION - EMORY COURSES
  emoryCourses: {
    core: [
      "ACT 200: Accounting - Understanding financial metrics for product decisions",
      "FIN 320: Corporate Finance - Essential for ROI and business cases",
      "MKT 340: Marketing Management - Core PM skill for customer needs",
      "ISOM 351: Process and Systems Management - Product development processes",
      "OAM 330/331: Organization and Strategic Management - Leadership skills"
    ],
    pmFocused: [
      "MKT 347: Product and Brand Management - Direct PM skills and product development",
      "MKT 345: Advanced Marketing Strategy - Product lifecycle management",
      "MKT 342: Data Driven Market Intelligence - Customer insights and research",
      "MKT 443: Monetization and Pricing Strategy - Product pricing decisions",
      "MKT 499R: Monetizing Innovations - Launching new products",
      "ISOM 352: Applied Data Analytics with Coding - Python and SQL for PMs",
      "ISOM 456: Business Data Analytics - Product metrics analysis",
      "ISOM 355: Appcology - Digital products and platforms",
      "ISOM 450: Foundations of Digital Enterprises - Digital product strategy",
      "OAM 436: Entrepreneurship - Product innovation mindset",
      "OAM 438: Management Consulting - Problem-solving frameworks",
      "FIN 322: Strategic Valuation - Assessing product value and ROI"
    ],
    immersive: [
      "MKT 442: Marketing Consulting Practicum - Real client projects",
      "ISOM 356: Think.Code.Make - Build actual products",
      "OAM 471: Applied Entrepreneurship - Launch your own product",
      "BUS 399R: Building AI Solutions - Develop AI products"
    ],
    recommendedPaths: [
      "Marketing + ISOM depth: Combines customer focus with technical skills for tech PM",
      "Marketing + Entrepreneurship: Perfect for product innovation",
      "Business Analytics + Marketing: Data-driven PM approach",
      "Consulting + Marketing: Strong problem-solving and customer focus"
    ]
  }
};

// ENHANCED Search function to handle course queries better
function searchKnowledge(query) {
  const results = [];
  const queryLower = query.toLowerCase();
  const queryWords = queryLower.split(' ');
  
  // Special handling for course-related queries
  if (queryWords.some(word => ['course', 'class', 'curriculum', 'major', 'study'].includes(word))) {
    // Return course information
    if (pmoryKnowledge.emoryCourses) {
      if (queryWords.some(word => ['core', 'foundation', 'basic'].includes(word))) {
        pmoryKnowledge.emoryCourses.core.forEach(course => {
          results.push(`Core Course: ${course}`);
        });
      } else if (queryWords.some(word => ['pm', 'product', 'management'].includes(word))) {
        pmoryKnowledge.emoryCourses.pmFocused.slice(0, 5).forEach(course => {
          results.push(`PM Course: ${course}`);
        });
      } else {
        // Return a mix of recommendations
        results.push(`PM Course: ${pmoryKnowledge.emoryCourses.pmFocused[0]}`);
        results.push(`Immersive: ${pmoryKnowledge.emoryCourses.immersive[0]}`);
        results.push(`Path: ${pmoryKnowledge.emoryCourses.recommendedPaths[0]}`);
      }
    }
  }
  
  // Continue with existing search logic for other queries
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
  
  // Remove duplicates and limit results
  return [...new Set(results)].slice(0, 5);
}

// ENHANCED Claude system prompt to include course knowledge
async function callClaude(message, knowledgeContext) {
  const apiKey = process.env.ANTHROPIC_API_KEY;
  
  console.log('API Key present:', apiKey ? 'Yes' : 'No');
  
  if (!apiKey) {
    throw new Error('Anthropic API key not configured');
  }
  
  const systemPrompt = `You are a helpful AI assistant for PMory, specializing in Product Management guidance for Emory University students.

PMory Knowledge Base Context:
${knowledgeContext}

IMPORTANT Emory Course Information:
- Core PM courses: MKT 347 (Product Management), MKT 345 (Marketing Strategy), ISOM 352 (Data Analytics)
- Best depth combinations: Marketing + ISOM for tech PM roles
- Immersive experiences available: Marketing Consulting Practicum, Think.Code.Make

Use the provided knowledge base context when relevant, and supplement with your general knowledge. Always be encouraging and specific in your advice for Emory students. When discussing courses, provide specific course codes and titles.`;

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

  // Rest of your existing Claude API call code remains the same
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

// Your handler remains mostly the same
exports.handler = async (event) => {
  // Your existing CORS and handler code stays exactly the same
  const corsHeaders = {
    'Content-Type': 'application/json',
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Headers': 'Content-Type, Authorization, X-Requested-With',
    'Access-Control-Allow-Methods': 'GET, POST, OPTIONS, PUT, DELETE',
    'Access-Control-Max-Age': '86400'
  };

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
    const httpMethod = event.requestContext?.http?.method || event.httpMethod || 'GET';
    const rawPath = event.requestContext?.http?.path || event.path || '/';
    const cleanPath = rawPath.replace(/^\/+/, '');

    if (cleanPath === '' && httpMethod === 'GET') {
      response.body = JSON.stringify({
        message: 'PMory AI - Real Claude Sonnet 4 with Emory Courses!',
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
        message: 'Claude Sonnet 4 connection ready with Emory course data',
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
      
      const knowledgeResults = searchKnowledge(message);
      const knowledgeContext = knowledgeResults.length > 0 
        ? knowledgeResults.join('\n') 
        : 'No specific PMory knowledge found for this query.';

      console.log('Knowledge results:', knowledgeResults);
      
      const claudeResponse = await callClaude(message, knowledgeContext);
      
      if (claudeResponse.content && claudeResponse.content[0]) {
        response.body = JSON.stringify({ 
          response: claudeResponse.content[0].text,
          knowledge_used: knowledgeResults.length > 0,
          rag_results: knowledgeResults,
          ai_model: 'Claude Sonnet 4',
          system: 'Real AI with RAG and Emory Courses'
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
