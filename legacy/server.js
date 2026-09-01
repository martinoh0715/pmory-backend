const express = require('express');
const cors = require('cors');
const bodyParser = require('body-parser');
require('dotenv').config();

const app = express();
const PORT = process.env.PORT || 3001;

// Middleware
app.use(cors());
app.use(bodyParser.json());
app.use(bodyParser.urlencoded({ extended: true }));

// Simple knowledge base (this is our RAG data)
const knowledgeBase = {
  pmBasics: {
    definition: "Product Management is the practice of strategically driving the development, market launch, and continual support and improvement of a company's products.",
    responsibilities: ["Strategic Planning", "Market Research", "Feature Prioritization", "Cross-functional Collaboration", "Data Analysis", "User Advocacy"]
  },
  emoryAdvantages: [
    "Strong business foundation from Goizueta Business School",
    "Analytical thinking from rigorous coursework", 
    "Leadership experience from various programs",
    "Network of successful alumni in tech industry"
  ],
  interviewTips: [
    "Use the STAR method for behavioral questions",
    "Practice product design with CIRCLES framework",
    "Prepare quantifiable examples of your impact",
    "Show analytical thinking and user empathy"
  ]
};

// AI Chat endpoint
app.post('/api/chat', async (req, res) => {
  try {
    const { message } = req.body;
    
    if (!message) {
      return res.status(400).json({ error: 'Message is required' });
    }

    // Simple response for now - we'll make it smarter later
    const responses = [
      "For PM interviews at tech companies, focus on demonstrating your analytical skills from your Emory business background. Use the STAR method to structure your answers.",
      "When building your PM resume, highlight any data analysis projects, leadership roles, and cross-functional collaboration from your Emory experience.",
      "Product Management combines business strategy, user empathy, and technical understanding. Your Emory business education gives you a strong foundation in the strategy component.",
      "For product design questions, try the CIRCLES method: Comprehend the situation, Identify the customer, Report customer needs, Cut through prioritization, List solutions, Evaluate tradeoffs, Summarize."
    ];
    
    const randomResponse = responses[Math.floor(Math.random() * responses.length)];
    
    res.json({ response: randomResponse });

  } catch (error) {
    console.error('Chat error:', error);
    res.status(500).json({ error: 'Internal server error' });
  }
});

// Home route
app.get('/', (req, res) => {
  res.json({ 
    message: 'PMory Backend API is running!',
    endpoints: {
      health: '/health',
      chat: '/api/chat (POST)'
    }
  });
});
// Health check
app.get('/health', (req, res) => {
  res.json({ status: 'OK', message: 'PMory Backend is running' });
});

app.listen(PORT, () => {
  console.log(`PMory Backend running on port ${PORT}`);
});
