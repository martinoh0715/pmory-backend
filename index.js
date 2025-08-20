const express = require('express');
const cors = require('cors');
const serverless = require('serverless-http');
const app = express();

// Enhanced CORS configuration
app.use(cors({
    origin: '*',
    methods: ['GET', 'POST', 'OPTIONS'],
    allowedHeaders: ['Content-Type', 'Authorization'],
    credentials: false
}));

// Handle preflight requests
app.options('*', cors());

app.use(express.json());

// Simple knowledge base for PMory
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

// Routes
app.get('/', (req, res) => {
  res.json({ 
    message: 'PMory Backend API is running on AWS Lambda!',
    endpoints: {
      health: '/health',
      chat: '/api/chat (POST)'
    }
  });
});

app.get('/health', (req, res) => {
  res.json({ status: 'OK', message: 'PMory Backend is running' });
});

app.post('/api/chat', async (req, res) => {
  try {
    const { message } = req.body;
    
    if (!message) {
      return res.status(400).json({ error: 'Message is required' });
    }

    // Simple AI-like responses based on keywords
    let response = "I'm here to help with Product Management guidance for Emory students!";
    
    const msgLower = message.toLowerCase();
    
    if (msgLower.includes('interview') || msgLower.includes('preparation')) {
      response = "For PM interviews, focus on demonstrating your analytical skills from your Emory business background. Use the STAR method (Situation, Task, Action, Result) to structure your behavioral answers. Practice product design questions using the CIRCLES framework.";
    } else if (msgLower.includes('resume')) {
      response = "When building your PM resume, highlight any data analysis projects, leadership roles, and cross-functional collaboration from your Emory experience. Quantify your achievements and show impact. Include any consulting, case competition, or analytics coursework.";
    } else if (msgLower.includes('skills') || msgLower.includes('skill')) {
      response = "Essential PM skills include: analytical thinking, communication, leadership, technical understanding, user empathy, and business acumen. Your Emory business education gives you a strong foundation in strategy and analysis.";
    } else if (msgLower.includes('emory')) {
      response = "As an Emory student, you have unique advantages: strong business foundation from Goizueta, analytical thinking from rigorous coursework, leadership experience, and access to a powerful alumni network in tech.";
    } else if (msgLower.includes('product') && msgLower.includes('management')) {
      response = "Product Management combines business strategy, user empathy, and technical understanding. PMs act as the bridge between business, technology, and user experience to drive product success.";
    }
    
    res.json({ response });

  } catch (error) {
    console.error('Chat error:', error);
    res.status(500).json({ error: 'Internal server error' });
  }
});

module.exports.handler = serverless(app);
