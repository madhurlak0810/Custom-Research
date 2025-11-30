class ResearchAssistantUI {
    constructor() {
        this.apiEndpoint = '';
        this.currentTopic = 'All Topics';
        this.topics = [];
        
        this.initializeEventListeners();
        this.loadConfig();
        this.loadTopics();
    }

    initializeEventListeners() {
        // Configuration
        document.getElementById('saveConfig').addEventListener('click', () => this.saveConfig());
        document.getElementById('apiEndpoint').addEventListener('input', () => this.validateConfig());

        // Ingestion
        document.getElementById('ingestBtn').addEventListener('click', () => this.ingestPapers());

        // Topics
        document.getElementById('refreshTopics').addEventListener('click', () => this.loadTopics());

        // Chat
        document.getElementById('sendBtn').addEventListener('click', () => this.sendMessage());
        document.getElementById('chatInput').addEventListener('keypress', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                this.sendMessage();
            }
        });

        // Auto-resize chat input
        document.getElementById('chatInput').addEventListener('input', (e) => {
            e.target.style.height = 'auto';
            e.target.style.height = e.target.scrollHeight + 'px';
        });
    }

    validateConfig() {
        const endpoint = document.getElementById('apiEndpoint').value;
        const chatInput = document.getElementById('chatInput');
        const sendBtn = document.getElementById('sendBtn');
        
        if (endpoint && this.isValidUrl(endpoint)) {
            chatInput.disabled = false;
            sendBtn.disabled = false;
            chatInput.placeholder = "Ask a question about the research papers...";
        } else {
            chatInput.disabled = true;
            sendBtn.disabled = true;
            chatInput.placeholder = "Please configure API endpoint first...";
        }
    }

    isValidUrl(string) {
        try {
            new URL(string);
            return true;
        } catch (_) {
            return false;
        }
    }

    saveConfig() {
        const endpoint = document.getElementById('apiEndpoint').value;
        if (!endpoint || !this.isValidUrl(endpoint)) {
            this.showStatus('ingestStatus', 'Please enter a valid API endpoint', 'error');
            return;
        }

        this.apiEndpoint = endpoint.replace(/\/$/, ''); // Remove trailing slash
        localStorage.setItem('apiEndpoint', this.apiEndpoint);
        this.showStatus('ingestStatus', 'Configuration saved successfully!', 'success');
        this.validateConfig();
        this.loadTopics();
    }

    loadConfig() {
        // Check for auto-generated config first
        if (typeof window.CONFIG !== 'undefined' && window.CONFIG.apiEndpoint) {
            document.getElementById('apiEndpoint').value = window.CONFIG.apiEndpoint;
            this.apiEndpoint = window.CONFIG.apiEndpoint;
            if (window.CONFIG.autoLoad) {
                this.saveConfig();
            }
            this.validateConfig();
            return;
        }
        
        // Fallback to localStorage
        const savedEndpoint = localStorage.getItem('apiEndpoint');
        if (savedEndpoint) {
            document.getElementById('apiEndpoint').value = savedEndpoint;
            this.apiEndpoint = savedEndpoint;
            this.validateConfig();
        }
    }

    async loadTopics() {
        if (!this.apiEndpoint) {
            this.updateTopicsList([]);
            return;
        }

        try {
            // Since we don't have a topics endpoint, we'll simulate it
            // In a real implementation, you'd add a /topics endpoint to your API
            const topics = this.getStoredTopics();
            this.topics = topics;
            this.updateTopicsList(topics);
        } catch (error) {
            console.error('Error loading topics:', error);
            this.updateTopicsList([]);
        }
    }

    getStoredTopics() {
        // Simulate topics based on common research areas
        // In production, this would come from your database
        const defaultTopics = [
            'All Topics',
            'Machine Learning',
            'Quantum Computing',
            'Computer Vision',
            'Natural Language Processing',
            'Artificial Intelligence',
            'Deep Learning',
            'Reinforcement Learning'
        ];
        
        const storedTopics = JSON.parse(localStorage.getItem('researchTopics') || '[]');
        return [...new Set([...defaultTopics, ...storedTopics])];
    }

    updateTopicsList(topics) {
        const topicsList = document.getElementById('topicsList');
        
        if (topics.length === 0) {
            topicsList.innerHTML = '<div class="topic-item loading">No topics available</div>';
            return;
        }

        topicsList.innerHTML = topics.map(topic => 
            `<div class="topic-item ${topic === this.currentTopic ? 'active' : ''}" 
                  onclick="ui.selectTopic('${topic}')">
                ${topic}
             </div>`
        ).join('');
    }

    selectTopic(topic) {
        this.currentTopic = topic;
        document.getElementById('currentTopic').textContent = topic;
        this.updateTopicsList(this.topics);
    }

    async ingestPapers() {
        const query = document.getElementById('query').value.trim();
        const maxPapers = parseInt(document.getElementById('maxPapers').value);
        
        if (!query) {
            this.showStatus('ingestStatus', 'Please enter a search query', 'error');
            return;
        }

        if (!this.apiEndpoint) {
            this.showStatus('ingestStatus', 'Please configure API endpoint first', 'error');
            return;
        }

        const ingestBtn = document.getElementById('ingestBtn');
        ingestBtn.disabled = true;
        ingestBtn.innerHTML = '<i class="loading-spinner"></i> Ingesting...';
        
        this.showStatus('ingestStatus', 'Fetching and processing papers...', 'loading');

        try {
            const response = await fetch(`${this.apiEndpoint}/ingest`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    query: query,
                    max_papers: maxPapers
                })
            });

            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            const result = await response.json();
            
            // Store the topic for future reference
            if (result.topic) {
                const storedTopics = JSON.parse(localStorage.getItem('researchTopics') || '[]');
                if (!storedTopics.includes(result.topic)) {
                    storedTopics.push(result.topic);
                    localStorage.setItem('researchTopics', JSON.stringify(storedTopics));
                }
                this.loadTopics();
            }

            this.showStatus('ingestStatus', 
                `Successfully processed ${result.processed_count} papers for topic: ${result.topic}`, 
                'success'
            );

            // Clear the query input
            document.getElementById('query').value = '';

        } catch (error) {
            console.error('Error ingesting papers:', error);
            this.showStatus('ingestStatus', 
                `Error: ${error.message}`, 
                'error'
            );
        } finally {
            ingestBtn.disabled = false;
            ingestBtn.innerHTML = '<i class="fas fa-download"></i> Ingest Papers';
        }
    }

    async sendMessage() {
        const chatInput = document.getElementById('chatInput');
        const message = chatInput.value.trim();
        
        if (!message) return;
        if (!this.apiEndpoint) {
            this.addMessage('Please configure API endpoint first', 'bot');
            return;
        }

        // Add user message
        this.addMessage(message, 'user');
        chatInput.value = '';
        
        // Add loading message
        const loadingId = this.addMessage('Thinking...', 'bot', true);

        try {
            const response = await fetch(`${this.apiEndpoint}/chat`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    query: message,
                    topic: this.currentTopic !== 'All Topics' ? this.currentTopic : undefined,
                    top_k: 5
                })
            });

            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            const result = await response.json();
            
            // Remove loading message
            document.getElementById(loadingId).remove();
            
            // Add bot response with sources
            this.addMessage(result.response, 'bot', false, result.sources);

        } catch (error) {
            console.error('Error sending message:', error);
            document.getElementById(loadingId).remove();
            this.addMessage(`Error: ${error.message}`, 'bot');
        }
    }

    addMessage(content, sender, isLoading = false, sources = null) {
        const chatMessages = document.getElementById('chatMessages');
        const messageId = 'msg_' + Date.now() + '_' + Math.random().toString(36).substr(2, 9);
        
        const messageDiv = document.createElement('div');
        messageDiv.className = `message ${sender}-message`;
        messageDiv.id = messageId;
        
        let icon = sender === 'user' ? 'fas fa-user' : 'fas fa-robot';
        if (isLoading) {
            icon = 'loading-spinner';
            content += ' <span class="loading-spinner"></span>';
        }

        let sourcesHtml = '';
        if (sources && sources.length > 0) {
            sourcesHtml = `
                <div class="sources">
                    <h4><i class="fas fa-book"></i> Sources:</h4>
                    ${sources.map(source => `
                        <div class="source-item">
                            <div class="source-title">${source.paper_title}</div>
                            <div class="source-details">
                                <span>Similarity: ${(source.similarity * 100).toFixed(1)}%</span>
                                <a href="${source.url}" target="_blank" style="color: #667eea;">
                                    <i class="fas fa-external-link-alt"></i> View Paper
                                </a>
                            </div>
                        </div>
                    `).join('')}
                </div>
            `;
        }

        messageDiv.innerHTML = `
            <div class="message-content">
                <i class="${icon}"></i>
                <div>
                    <p>${content}</p>
                    ${sourcesHtml}
                </div>
            </div>
        `;

        chatMessages.appendChild(messageDiv);
        chatMessages.scrollTop = chatMessages.scrollHeight;
        
        return messageId;
    }

    showStatus(elementId, message, type) {
        const statusElement = document.getElementById(elementId);
        statusElement.textContent = message;
        statusElement.className = `status ${type}`;
        
        if (type === 'success') {
            setTimeout(() => {
                statusElement.textContent = '';
                statusElement.className = 'status';
            }, 5000);
        }
    }
}

// Initialize the UI when the page loads
let ui;
document.addEventListener('DOMContentLoaded', () => {
    ui = new ResearchAssistantUI();
});

// Make UI instance globally available for onclick handlers
window.ui = ui;