# data-review-ast
for ephicacy-vpn
# Data Review Assistant

An intelligent multi-study data analysis application that allows users to query data using natural language, powered by Amazon Bedrock with Claude. This application enables researchers to manage multiple studies, upload data files, and analyze them through an intuitive chat interface with automatic visualization generation and comprehensive reporting capabilities.

## Key Features

### Study Management
- **Multi-Study Support**: Create and manage multiple research studies independently
- **Study Isolation**: Each study maintains its own data, protocols, and chat history
- **Study Switching**: Seamlessly switch between different studies
- **Guided Study Creation**: Interactive workflow for setting up new studies

### Data Management
- Upload CSV or Excel files (single or multiple)
- Support for protocol PDF files per study
- Store data securely in isolated SQLite databases per study
- Automatic table creation and data validation
- Study-specific data directory structure

### Intelligent Querying
- Natural language query interface with chat-based interaction
- Automatic SQL query generation using Claude AI
- Multi-query approach for complex analysis across all database tables
- Generalized example questions that work with any database structure
- Context-aware query processing with intent detection

### Visualization & Analysis
- Dynamic visualization generation based on query context
- Support for multiple chart types:
  - Bar charts
  - Pie charts  
  - Line graphs
  - Scatter plots
  - Histograms
  - Box plots
- Automatic chart type selection based on data characteristics

### Export & Reporting
- Enhanced HTML export of complete chat history
- Professional styling with custom CSS
- Downloadable chat transcripts with embedded visualizations
- Protocol-based summaries for clinical data analysis

## Setup and Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/Zero2AI/medinsight.git
   cd medinsight
   ```

2. **Create and activate virtual environment**
   ```powershell
   python -m venv prototypevenv
   .\prototypevenv\Scripts\Activate.ps1
   ```

3. **Install dependencies**
   ```powershell
   pip install -r requirements.txt
   ```

4. **Configure environment variables**
   - Create a `.env` file in the root directory
   - Add your AWS credentials:
     ```
     AWS_ACCESS_KEY_ID=your_key_here
     AWS_SECRET_ACCESS_KEY=your_secret_here
     AWS_DEFAULT_REGION=us-east-1
     ```

5. **Launch the application**
   ```powershell
   streamlit run app.py
   ```

## How to Use

### Getting Started
1. **Welcome Screen**: When you first open the app, you'll see a welcome screen
2. **Create a Study**: Use chat commands like "create new study" or use the guided workflow
3. **Upload Data**: Say "upload data file" or use the file upload interface
4. **Start Analyzing**: Ask questions about your data in natural language

### Study Management
- **Create New Study**: Type "create new study" and follow the guided workflow
- **Switch Studies**: Type "switch to [study name]" or "list studies" to see available options
- **Upload Files**: Use "upload data file" or "upload protocol" commands
- **Study Isolation**: Each study maintains separate data, chat history, and protocols

### Querying Your Data
- **Natural Language**: Ask questions in plain English about your data
- **Example Questions**: Click on suggested questions in the sidebar:
  - "Show me all tables in the database with their row and column counts"
  - "What are the column names and data types for each table?"
  - "Are there any duplicate records in any of the tables?"
  - "Show me a summary of the data in each table"
- **Advanced Analysis**: Ask complex questions spanning multiple tables
- **Visualization Requests**: Request charts and graphs for data insights

### Chat Interface Features
- **Intent Detection**: The system understands different types of requests
- **Context Awareness**: Maintains conversation context across queries
- **Interactive Workflows**: Guided processes for study creation and file uploads
- **Export Options**: Download complete chat history as formatted HTML

## Project Structure

```
medinsight/
├── app.py                      # Main Streamlit application with multi-study support
├── requirements.txt            # Project dependencies
├── run_app.bat                # Windows batch file to run the application
├── stop_streamlit.bat         # Windows batch file to stop Streamlit server
├── .env                       # Environment variables (AWS credentials)
├── README.md                  # Project documentation
├── data/                      # Default data directory (legacy mode)
│   └── app.db                 # Default SQLite database file
├── protocols/                 # Default protocols directory (legacy mode)
│   ├── protocol.pdf           # Default protocol file
│   └── QUESTIONS.csv          # Column mapping configuration
├── studies/                   # Multi-study directory structure
│   ├── [study_name_1]/        # Individual study directory
│   │   ├── data/              # Study-specific data
│   │   │   └── [study].db     # Study-specific SQLite database
│   │   └── protocols/         # Study-specific protocols
│   │       ├── protocol.pdf   # Study protocol file
│   │       └── QUESTIONS.csv  # Study-specific column mappings
│   └── [study_name_2]/        # Additional studies...
└── tools/                     # Application modules
    ├── __init__.py
    ├── db_utils.py            # Database operations with multi-study support
    ├── data_tools.py          # Data processing utilities
    └── llm_tools.py           # AI query generation and chat processing
```

## UI/UX Features

- **Modern Dark Theme**: Professional interface optimized for data analysis
- **Chat-Based Interface**: Intuitive conversational interaction model
- **Interactive Workflows**: Guided study creation and file upload processes
- **Study Management**: Easy switching between multiple research studies
- **Welcome Screen**: Streamlined onboarding experience
- **Sidebar Integration**: Quick access to example questions and commands
- **Real-time Feedback**: Toast notifications and status updates
- **Responsive Design**: Adaptable interface for various screen sizes
- **Professional Export**: High-quality HTML exports with custom styling
- **Context Awareness**: System remembers conversation context and study state

## Chat Commands

The application supports natural language commands for easy interaction:

- **Study Management**:
  - `create new study`
  - `list studies` or `show available studies`
  - `switch to [study name]`
  
- **File Operations**:
  - `upload data file`
  - `upload protocol`
  - `upload csv file`
  - `upload excel file`

- **General Commands**:
  - `cancel` - Cancel current workflow
  - `help` - Get assistance
  - Example questions available in sidebar

## Security & Privacy Features

- **Local Data Storage**: All data remains on your local machine
- **Study Isolation**: Each study's data is completely separate
- **Secure SQL Generation**: Query sanitization and validation
- **No Data Transmission**: Only table schemas (not actual data) sent to AI
- **Environment Protection**: AWS credentials stored securely in .env file
- **Database Encryption**: SQLite databases with secure access patterns

## Technical Stack

- **Frontend**: Streamlit with custom CSS styling
- **Database**: SQLite with multi-study architecture
- **AI/ML**: Amazon Bedrock with Claude AI models
- **Data Processing**: Pandas for data manipulation and analysis
- **Visualization**: Plotly Express for interactive charts
- **API Integration**: LangChain and boto3 for AWS services
- **PDF Processing**: PyPDF2 for protocol document handling
- **Export Formats**: Custom HTML/CSS for chat exports, ReportLab for PDF generation
- **Session Management**: Streamlit session state for multi-study support
- **File Handling**: Support for CSV, Excel (xlsx/xls), and PDF formats

## Architecture Highlights

- **Multi-Study Design**: Independent study environments with isolated data and chat histories
- **Intent Detection**: Advanced natural language understanding for command processing
- **Conversation Context**: Maintains state across chat interactions
- **Workflow Management**: Guided processes for complex operations
- **Database Abstraction**: Flexible database layer supporting multiple study contexts
- **Modular Structure**: Separate modules for database, LLM, and data processing operations

## Recent Updates

- **Multi-Study Support**: Complete rewrite to support multiple independent studies
- **Enhanced Chat Interface**: Advanced conversational AI with intent detection
- **Guided Workflows**: Interactive study creation and file upload processes
- **Study Management**: Full CRUD operations for research studies
- **Improved Export**: Enhanced HTML export with better formatting and styling
- **Generalized Examples**: Database-agnostic example questions for broader applicability
- **Welcome Screen**: Streamlined onboarding experience for new users
- **Context Management**: Persistent conversation context across study switches

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/new-feature`)
3. Commit your changes (`git commit -am 'Add new feature'`)
4. Push to the branch (`git push origin feature/new-feature`)
5. Create a Pull Request

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Support

For support, feature requests, or bug reports, please open an issue on the GitHub repository.
