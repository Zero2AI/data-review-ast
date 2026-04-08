"""
LLM tools for SQL generation and query processing.
"""
from typing import Dict, List, Optional
import os
import boto3
import json
import pandas as pd

from langchain_core.prompts import PromptTemplate
from langchain_core.output_parsers import StrOutputParser
#from langchain.globals import set_verbose
from dotenv import load_dotenv


#set_verbose(False)
verbose = False

load_dotenv()

def read_pdf_content(file_path):
    """Read content from a PDF file."""
    try:
        from PyPDF2 import PdfReader
        
        # Read PDF content
        with open(file_path, 'rb') as f:
            reader = PdfReader(f)
            content = ""
            for page in reader.pages:
                content += page.extract_text() + "\n"
        return content
    except Exception as e:
        return f"Error reading PDF file: {str(e)}"

def get_annotation_content():
    """Get the content of the annotation file from the protocols directory."""
    protocol_dir = os.path.join(os.getcwd(), "protocols")
    annotation_file_path = os.path.join(protocol_dir, "annotation.pdf")
    
    # Check if annotation file exists
    if not os.path.exists(annotation_file_path):
        return ""
    
    # Read annotation file content
    if annotation_file_path.endswith('.pdf'):
        return read_pdf_content(annotation_file_path)
    else:
        try:
            with open(annotation_file_path, 'r', encoding='utf-8', errors='ignore') as f:
                return f.read()
        except Exception as e:
            return f"Error reading annotation file: {str(e)}"
            
def process_annotation_content(content):
    """
    Process annotation content to extract mappings between common terms and database columns.
    This helps structure the annotation content to make it more useful for the LLM.
    """
    if not content:
        return {"formatted_content": "", "mapping_examples": ""}
    
    # Initialize result
    result = {
        "formatted_content": content,
        "mapping_examples": ""
    }
    
   
    mapping_lines = []
    lines = content.split('\n')
    
    for line in lines:
        line = line.strip()
        # Look for potential mapping patterns
        if ':' in line or '-' in line or '=' in line:
            if not line.startswith('#') and not line.startswith('//'):  # Skip comments
                mapping_lines.append(line)    # If we found potential mappings, format them specially
    if mapping_lines:
        result["mapping_examples"] = "Examples of term to column mappings from annotation file:\n"
        result["mapping_examples"] += "\n".join(mapping_lines[:10])  # Limit to first 10 examples
          # Add specific example for Bicarbonate to LBORRES if it appears to be in the content
        if "bicarbonate" in content.lower() and "lborres" in content.lower():
            result["mapping_examples"] += "\n\nSpecific example: When a user asks about 'Bicarbonate', look for the column 'LBORRES' in the database."
            
    # Always initialize mapping_examples if it's empty
    if not result["mapping_examples"]:
        result["mapping_examples"] = "Term to column mappings:\n"
          # Always add specific mapping for patient IDs, regardless of whether other mappings were found
    result["mapping_examples"] += "\n\nCRITICAL MAPPING: For ALL patient identification, ALWAYS use the column 'patient_display_id_full'. NEVER use 'patient_id' in any query. Replace ANY occurrence of 'patient_id' with 'patient_display_id_full' without exception."
      # Add specific mapping for lab value and unit columns pairing
    result["mapping_examples"] += "\n\nCRITICAL MAPPING: Lab values MUST ALWAYS be paired with their unit columns in SELECT statements. Examples of common pairs: LBORRES (value) with LBORRESU (unit), VSORRES (value) with VSORRESU (unit). Never select a value column without its corresponding unit column."
    
    # Add specific mapping for unit column case sensitivity
    result["mapping_examples"] += "\n\nCRITICAL MAPPING: Unit columns have case-sensitive values - columns like WEIGHTU store units in UPPERCASE (e.g., 'LB', 'KG'), while corresponding _R columns (like WEIGHTU_R) store units in lowercase (e.g., 'lb', 'kg'). Always use the correct column and case when searching for units."
    
    # Add specific mapping for lab test values appearing in both LBTEST and LBTEST_R columns
    result["mapping_examples"] += "\n\nIMPORTANT: For lab test values like BICARBONATE, search in BOTH the 'LBTEST' AND 'LBTEST_R' columns. Always check both columns using OR conditions in a single query. For example: WHERE (LBTEST LIKE '%BICARBONATE%' OR LBTEST_R LIKE '%BICARBONATE%')."
    
    # Add general instruction for searching across multiple potential columns
    result["mapping_examples"] += "\n\nIMPORTANT: When searching for a term that might appear in different columns, use OR conditions within a SINGLE query. For example: WHERE (column1 LIKE '%term%' OR column2 LIKE '%term%') instead of creating multiple separate queries. This ensures efficient searching across alternative column locations."
    
    return result

def detect_chat_intent(message: str) -> dict:
    """
    Detect user intent from chat message using Claude.
    Returns intent classification and extracted parameters.
    """
    try:
        # Load environment variables
        load_dotenv()
        
        # Initialize Bedrock client
        boto3.setup_default_session(
            aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
            aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
            region_name=os.getenv('AWS_DEFAULT_REGION')
        )
        
        bedrock_client = boto3.client(
            service_name='bedrock-runtime',
            region_name=os.getenv('AWS_DEFAULT_REGION')
        )
        
        system_prompt = """You are an intent classification system for a clinical data analysis application. 
        Classify user messages into one of these categories and extract relevant parameters:

        INTENTS:
        1. data_query - User wants to query/analyze data (includes SQL questions, data exploration)
        2. study_management - User wants to create, switch, or manage studies
        3. file_upload - User wants to upload data files or protocols
        4. settings - User wants to change application settings or configurations
        5. help - User needs help or information about the application
        6. chat - General conversation or unclear intent

        PARAMETERS TO EXTRACT:
        - study_name: If user mentions a specific study name
        - file_type: If user mentions uploading specific file types (csv, excel, pdf)
        - table_name: If user mentions specific database tables
        - action: Specific action they want to perform (create, delete, upload, switch, etc.)

        Return response as JSON with: {"intent": "intent_name", "confidence": 0.0-1.0, "parameters": {...}, "explanation": "brief reason"}

        EXAMPLES:
        "Show me all patients" -> {"intent": "data_query", "confidence": 0.95, "parameters": {}, "explanation": "User wants to query patient data"}
        "Create new study called Trial123" -> {"intent": "study_management", "confidence": 0.9, "parameters": {"study_name": "Trial123", "action": "create"}, "explanation": "User wants to create new study"}
        "Create a new study" -> {"intent": "study_management", "confidence": 0.95, "parameters": {"action": "create"}, "explanation": "User wants to create new study"}
        "lets work on new study today" -> {"intent": "study_management", "confidence": 0.9, "parameters": {"action": "create"}, "explanation": "User wants to create new study"}
        "today i feel like working on new study" -> {"intent": "study_management", "confidence": 0.9, "parameters": {"action": "create"}, "explanation": "User wants to create new study"}
        "work on new study" -> {"intent": "study_management", "confidence": 0.9, "parameters": {"action": "create"}, "explanation": "User wants to create new study"}
        "List all studies" -> {"intent": "study_management", "confidence": 0.9, "parameters": {"action": "list"}, "explanation": "User wants to see available studies"}
        "Switch to study ABC" -> {"intent": "study_management", "confidence": 0.9, "parameters": {"study_name": "ABC", "action": "switch"}, "explanation": "User wants to switch studies"}
        "Upload CSV file" -> {"intent": "file_upload", "confidence": 0.85, "parameters": {"file_type": "csv"}, "explanation": "User wants to upload data file"}
        "Upload data file" -> {"intent": "file_upload", "confidence": 0.85, "parameters": {"file_type": "data"}, "explanation": "User wants to upload data file"}
        """

        user_prompt = f"Classify this user message: '{message}'"

        # Prepare the request
        request_body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 1000,
            "system": system_prompt,
            "messages": [
                {
                    "role": "user",
                    "content": user_prompt
                }
            ],
            "temperature": 0.1,
            "top_p": 0.9
        }

        # Make the API call
        response = bedrock_client.invoke_model(
            modelId='us.anthropic.claude-sonnet-4-20250514-v1:0',
            contentType='application/json',
            accept='application/json',
            body=json.dumps(request_body)
        )

        # Parse response
        response_body = json.loads(response['body'].read())
        result_text = response_body['content'][0]['text']
        
        # Try to parse JSON response
        try:
            result = json.loads(result_text)
            return result
        except json.JSONDecodeError:
            # Fallback if JSON parsing fails
            return {
                "intent": "chat",
                "confidence": 0.5,
                "parameters": {},
                "explanation": "Could not parse intent"
            }
            
    except Exception as e:
        print(f"Error in intent detection: {e}")
        return {
            "intent": "chat",
            "confidence": 0.0,
            "parameters": {},
            "explanation": f"Error: {str(e)}"
        }

class SQLGenerator:    
    def __init__(self, temperature: float = 0.1, study_name: str = None):
        """Initialize the SQL Generator with Amazon Bedrock."""       
        boto3.setup_default_session(
            aws_access_key_id=os.getenv('AWS_ACCESS_KEY_ID'),
            aws_secret_access_key=os.getenv('AWS_SECRET_ACCESS_KEY'),
            region_name=os.getenv('AWS_DEFAULT_REGION')
        )
        
        self.bedrock_client = boto3.client(            
            service_name='bedrock-runtime',
            region_name=os.getenv('AWS_DEFAULT_REGION')
        )
        
        self.model_id = 'us.anthropic.claude-sonnet-4-20250514-v1:0'
        self.temperature = temperature
        self.study_name = study_name
        top_p = 0.9  # Set top_p for sampling          
        self.system_prompt = """You are an expert SQL query generator focused on generating precise, minimal queries. Follow these principles:
1. Write queries that ONLY include exactly what was asked for - no extra fields or joins
2. NEVER add JOINs unless explicitly requested in the question
3. Each table should be treated as a standalone data source first
4. Only combine tables when the user specifically asks to relate or compare data
5. Always translate domain terms to their correct database column names
6. ALWAYS use patient_display_id_full for ALL patient identification - NEVER use patient_id
7. For lab tests like BICARBONATE, always search both LBTEST and LBTEST_R columns using OR conditions
8. When JOINs are requested, fully qualify ALL column names with table names
9. CRITICAL: For ANY lab value column (e.g., LBORRES), ALWAYS include its corresponding unit column (e.g., LBORRESU) in the SELECT statement
10. NEVER make assumptions about unit conversions - do not automatically convert between units unless explicitly requested by the user
11. If a query mentions units, search for that exact value and unit without conversion
12. CRITICAL: For unit values, be aware of case sensitivity - columns like WEIGHTU store units in UPPERCASE (e.g., 'LB', 'KG'), while corresponding _R columns (like WEIGHTU_R) store units in lowercase (e.g., 'lb', 'kg'). Always use the correct column and case when searching for units
13. CRITICAL: For coded values like dose counts, search in the base column (e.g., EXCOUNT = '1') for numeric/coded values, and search in the _R column (e.g., EXCOUNT_R = '1st Dose') for descriptive labels. When users mention descriptive terms like "1st Dose", translate to the appropriate coded value in the base column or search the _R column specifically

SPECIAL CASE HANDLING:
14. When querying for MISSING VALUES, include full table name and additional context columns like timestamps, primary keys, and any related identifier columns
15. When detecting DUPLICATES, always include ALL primary key columns and relevant contextual fields to help identify why duplicates exist
16. For MULTI-TABLE queries, always fully qualify all column names with table names and include join conditions in the results"""
        
        # Get annotation content for the prompts
        self.annotation_content = get_annotation_content()
        
        # Process annotation content to extract mappings
        self.processed_annotations = process_annotation_content(self.annotation_content)        
        self.output_parser = StrOutputParser()
        
        # Update SQL prompt to include annotation information if available
        annotation_section = ""
        if self.annotation_content:
            annotation_section = f"""
IMPORTANT - Term to Database Column Mappings:
The annotation file provides mappings between common terms and database column names.
When writing SQL, translate common terms to their corresponding column names.

{self.processed_annotations["mapping_examples"]}

Full Annotation Reference:
{self.annotation_content}
"""
                
        self.sql_prompt = PromptTemplate(
            template=f"""You are an expert SQL query generator. Given the following:

Database Schema:
{{schema}}

{annotation_section}

User Question:
{{question}}

CRITICAL QUERY GENERATION RULES:

1. Basic Principles:
   - Generate minimal queries that do exactly what was asked for
   - Never add fields or joins that weren't requested
   - Keep queries as simple as possible
   - NEVER make assumptions about unit conversions
   - Do not automatically convert between units unless explicitly requested by the user

2. Table and Column Usage:
   - Start with a single table that has the needed data
   - Only use columns specifically mentioned in the question
   - Use schema-defined column names exactly
   - Check for all possible variations of values in the data (e.g., if searching for a specific value, consider common abbreviations or alternate forms)
   - Use OR conditions when searching for values that might have variations

3. Data Access Rules:
   - NO automatic table joins
   - NO extra columns "just in case"
   - NO combining data unless explicitly requested
   - If data is in one table, use only that table

4. When JOINs are Requested:
   - Only join when explicitly asked
   - Qualify all column names with table names
   - Use proper join conditions from schema
   - Document why each join is needed

Example Query Patterns:
1. Single Table (Preferred):
   -- For exact matches:
   SELECT column1 FROM table1 WHERE column2 = 'value';
   
   -- For values with variations:
   SELECT column1 FROM table1 WHERE column2 IN ('value1', 'value2')
   -- or --
   SELECT column1 FROM table1 WHERE column2 = 'value1' OR column2 = 'value2';
   
   -- For searching the same value across multiple columns:
   SELECT column1 FROM table1 WHERE (column2 LIKE '%value%' OR column3 LIKE '%value%');
   
   -- CRITICAL: For patient identification, ALWAYS use patient_display_id_full:
   -- CORRECT:
   SELECT patient_display_id_full FROM chemistry_cel WHERE condition;
   -- WRONG (NEVER DO THIS):
   -- SELECT patient_id FROM chemistry_cel WHERE condition;
     -- CRITICAL: For lab test values like BICARBONATE, always search both LBTEST and LBTEST_R:
   SELECT * FROM lab_results WHERE (LBTEST LIKE '%BICARBONATE%' OR LBTEST_R LIKE '%BICARBONATE%');
     -- CRITICAL: ALWAYS include unit columns with their corresponding value columns:
   -- CORRECT:
   SELECT patient_display_id_full, LBORRES, LBORRESU FROM lab_results WHERE condition;
   -- WRONG (NEVER DO THIS):
   -- SELECT patient_display_id_full, LBORRES FROM lab_results WHERE condition;
   
   -- CRITICAL: Unit columns have case-sensitive values:
   -- For uppercase units (stored in the base unit column):
   SELECT patient_display_id_full, WEIGHT, WEIGHTU FROM vital_signs_cel WHERE WEIGHTU = 'LB';
   -- For lowercase units (stored in the _R unit column):
   SELECT patient_display_id_full, WEIGHT, WEIGHTU_R FROM vital_signs_cel WHERE WEIGHTU_R = 'lb';

2. Multiple Tables (Only when asked):
   SELECT t1.column1, t2.column2 
   FROM table1 t1 
   JOIN table2 t2 ON t1.id = t2.id;
   Wrong: Don't automatically JOIN with other tables

2. "Compare bicarbonate values with patient demographics" 
   - Only NOW use JOIN because comparison was explicitly requested
   - Qualify all columns: chemistry_cel.patient_id, demographics.SEX, etc.

Special Case Instructions:
- For queries about MISSING VALUES: Include full table name (e.g., table_name.column_name) for all columns and include context columns like patient identifiers and date/time columns to provide more context.
- For queries about DUPLICATES: Always include ALL primary key columns and additional context columns that help identify the duplicates. Use COUNT(*) and GROUP BY for efficient duplicate detection.
- For MULTI-TABLE queries: Fully qualify ALL column names with table names (e.g., table1.column1, table2.column2) and include explicit join conditions.

Generate a SQL query that answers ONLY what was asked:
1. Efficient and optimized
2. Safe and follow best practices
3. Compatible with SQLite syntax
4. DO NOT include any comments in the query
5. DO NOT use markdown code blocks
6. Return ONLY the raw SQL query

Important SQLite Constraints:
- SQLite does NOT support STDDEV function
- SQLite does NOT allow nested aggregate functions

For outlier detection, use this pattern exactly (replacing 'column', 'table', and 'N' with actual values):

WITH mean_table AS (
  SELECT AVG(column) AS mean_value
  FROM table
),
samples AS (
  SELECT column, (column - (SELECT mean_value FROM mean_table)) * (column - (SELECT mean_value FROM mean_table)) AS squared_diff
  FROM table
),
variance_table AS (
  SELECT AVG(squared_diff) AS variance
  FROM samples
),
std_dev_table AS (
  SELECT SQRT((SELECT variance FROM variance_table)) AS std_dev
  FROM samples LIMIT 1
)
SELECT column, other_columns
FROM table
WHERE ABS(column - (SELECT mean_value FROM mean_table)) > N * (SELECT std_dev FROM std_dev_table);

Example format:
SELECT column FROM table WHERE condition;

SQL Query:""",
            input_variables=["schema", "question"]
        )
          
    def generate_sql(self, schema: str, question: str) -> str:
        """Generate SQL query from natural language question.
        
        Args:
            schema (str): Database schema information
            question (str): Natural language question to convert to SQL
            
        Returns:
            str: Generated SQL query
            
        Raises:
            Exception: If there's an error generating the SQL query
        """
        max_retries = 2
        retry_count = 0
        
        # Detect special cases for enhanced query handling
        is_missing_values = any(term in question.lower() for term in ["missing", "null", "empty", "absent", "not present"])
        is_duplicates = any(term in question.lower() for term in ["duplicate", "duplicates", "repeated", "unique", "distinct"])
        is_multi_table = any(term in question.lower() for term in [" join ", "across tables", "multiple tables", "between tables"])
        
        while retry_count <= max_retries:
            try:
                # Build special case instructions based on detected cases
                special_case_instructions = ""
                if is_missing_values:
                    special_case_instructions += "\nFor this MISSING VALUES query: Include full table name for all columns and include context columns like patient identifiers and date/time columns."
                if is_duplicates:
                    special_case_instructions += "\nFor this DUPLICATES query: Include ALL primary key columns and additional context columns that help identify the duplicates."
                if is_multi_table:
                    special_case_instructions += "\nFor this MULTI-TABLE query: Fully qualify ALL column names with table names and include explicit join conditions."
                
                # Append special case instructions to the question if needed
                enhanced_question = question
                if special_case_instructions:
                    enhanced_question = f"{question}\n{special_case_instructions}"
                
                formatted_prompt = self.sql_prompt.format(schema=schema, question=enhanced_question)
                
               
                payload = {
                    "anthropic_version": "bedrock-2023-05-31",
                    "max_tokens": 6000,
                    "temperature": self.temperature,
                    "system": self.system_prompt,
                    "messages": [
                        {
                            "role": "user",
                            "content": formatted_prompt
                        }
                    ]
                }
                
               
                response = self.bedrock_client.invoke_model(
                    modelId=self.model_id,
                    body=json.dumps(payload)
                )
                  # Parse the response
                response_body = json.loads(response['body'].read().decode('utf-8'))
                
                if 'content' not in response_body:
                    raise Exception(f"Unexpected response format: {response_body}")
                    
                raw_query = response_body['content'][0]['text']
                
                # Process completed successfully, break out of retry loop
                break
                
            except Exception as e:
                retry_count += 1
                if retry_count > max_retries:
                    # We've exhausted our retries, raise the exception
                    raise Exception(f"Error generating SQL query: {str(e)}")
                # Otherwise, we'll retry
        
        # Clean up the query
        clean_query = raw_query.replace("```sql", "").replace("```", "").strip()
        
        # Remove any explanatory text before actual SQL
        if "WITH" in clean_query:
            clean_query = clean_query[clean_query.find("WITH"):]
        elif "SELECT" in clean_query:
            clean_query = clean_query[clean_query.find("SELECT"):]
        
        # Remove comments and clean up the query
        clean_lines = []
        for line in clean_query.split("\n"):
            # Remove inline comments
            if "--" in line:
                line = line.split("--")[0]
            # Remove /* */ style comments
            if "/*" in line and "*/" in line:
                line = line[:line.find("/*")] + line[line.find("*/") + 2:]
            line = line.strip()
            if line:  # only keep non-empty lines
                clean_lines.append(line)
          # Join lines and ensure semicolon at the end
        final_query = " ".join(clean_lines).strip()
        if not final_query.endswith(";"):
            final_query += ";"
            
        return final_query
        
    def generate_multi_sql(self, schema: str, question: str) -> List[str]:
        """Generate multiple SQL queries from a complex natural language question.
        
        Args:
            schema (str): Database schema information
            question (str): Natural language question that may require multiple queries
            
        Returns:
            List[str]: List of generated SQL queries
            
        Raises:
            Exception: If there's an error generating the SQL queries
        """
        max_retries = 2
        retry_count = 0
        
        # Detect special cases for enhanced query handling
        is_missing_values = any(term in question.lower() for term in ["missing", "null", "empty", "absent", "not present"])
        is_duplicates = any(term in question.lower() for term in ["duplicate", "duplicates", "repeated", "unique", "distinct"])
        is_multi_table = any(term in question.lower() for term in [" join ", "across tables", "multiple tables", "between tables"])
          
        # Add annotation information if available
        annotation_section = ""        
        if self.annotation_content:
            annotation_section = f"""
IMPORTANT - Term to Database Column Mappings:
The annotation file provides mappings between common terms and database column names.
When writing SQL, translate common terms to their corresponding column names.

{self.processed_annotations["mapping_examples"]}

Full Annotation Reference:
{self.annotation_content}
"""
        
        # Create a specialized prompt for multi-query generation
        multi_sql_prompt = PromptTemplate(
            template=f"""You are an expert SQL query generator. Given the following:

Database Schema:
{{schema}}

{annotation_section}

User Question:
{{question}}

INSTRUCTIONS FOR TERM TRANSLATION:
1. First, identify any medical or domain-specific terms in the user question (like "Bicarbonate").
2. Check if these terms have corresponding database column names in the annotation file.
3. Use the database column names (like "LBORRES") in your query instead of the common terms.
4. Pay special attention to column names in the schema that might represent coded values.
5. CRITICAL: For ALL patient identification, ALWAYS use 'patient_display_id_full' - NEVER use 'patient_id'.
6. CRITICAL: For ANY lab value column (e.g., LBORRES), ALWAYS include its corresponding unit column (e.g., LBORRESU) in the SELECT statement.
7. NEVER make assumptions about unit conversions - do not automatically convert between units unless explicitly requested by the user.
8. If a query mentions units, search for that exact value and unit without conversion.
9. CRITICAL: For unit values, be aware of case sensitivity - columns like WEIGHTU store units in UPPERCASE (e.g., 'LB', 'KG'), while corresponding _R columns (like WEIGHTU_R) store units in lowercase (e.g., 'lb', 'kg'). Always use the correct column and case when searching for units.

CRITICAL: For lab test values like BICARBONATE, you MUST search in BOTH 'LBTEST' AND 'LBTEST_R' columns using OR conditions within a single query. For example, use: 
WHERE (LBTEST LIKE '%BICARBONATE%' OR LBTEST_R LIKE '%BICARBONATE%')

For example, if the question asks about "Bicarbonate values higher than 30", and the annotation indicates 
Bicarbonate data is stored in "LBORRES" column, your query should use "LBORRES" instead of searching for a column named "Bicarbonate".

Special Case Instructions:
- For queries about MISSING VALUES: Include full table name (e.g., table_name.column_name) for all columns and include context columns like patient identifiers and date/time columns to provide more context.
- For queries about DUPLICATES: Always include ALL primary key columns and additional context columns that help identify the duplicates. Use COUNT(*) and GROUP BY for efficient duplicate detection.
- For MULTI-TABLE queries: Fully qualify ALL column names with table names (e.g., table1.column1, table2.column2) and include explicit join conditions.

Break down this complex request into multiple SQL queries as needed. The queries should be:
1. Efficient and optimized
2. Safe and follow best practices
3. Compatible with SQLite syntax
4. Separated by "---QUERY_SEPARATOR---" in your response

Important SQLite Constraints:
- SQLite does NOT support STDDEV function
- SQLite does NOT allow nested aggregate functions

If the user's question requires multiple different queries (like getting missing data AND table descriptions),
create separate queries for each part of the request.

For questions about missing data and table descriptions, consider:
1. For missing data analysis:
   - Generate separate queries for each important table
   - Each query should count total rows and NULL values for key columns
   - Format: SELECT 'table_name' AS table_name, COUNT(*) AS total_rows, SUM(CASE WHEN col1 IS NULL THEN 1 ELSE 0 END) AS col1_null, ...

2. For table descriptions:
   - Include queries that show the table structure (PRAGMA table_info)
   - Include queries that show sample data from each table (SELECT * FROM table LIMIT 5)
   - Include summary statistics for numeric columns

Return ONLY the raw SQL queries separated by "---QUERY_SEPARATOR---". 
DO NOT include explanations, markdown code blocks, or comments.

Example response format:
SELECT patient_display_id_full, LBORRES, LBORRESU FROM chemistry_cel WHERE (LBTEST LIKE '%BICARBONATE%' OR LBTEST_R LIKE '%BICARBONATE%') AND CAST(LBORRES AS REAL) > 30;
---QUERY_SEPARATOR---
SELECT patient_display_id_full, WEIGHT, WEIGHTU FROM vital_signs_cel WHERE WEIGHTU = 'LB' AND CAST(WEIGHT AS REAL) > 250;
---QUERY_SEPARATOR---
SELECT patient_display_id_full, VSORRES, VSORRESU FROM vitals WHERE VSTESTCD = 'PULSE';

SQL Queries:""",
            input_variables=["schema", "question"]
        )
        
        while retry_count <= max_retries:
            try:
                # Build special case instructions based on detected cases
                special_case_instructions = ""
                if is_missing_values:
                    special_case_instructions += "\nFor this MISSING VALUES query: Include full table name for all columns and include context columns like patient identifiers and date/time columns."
                if is_duplicates:
                    special_case_instructions += "\nFor this DUPLICATES query: Include ALL primary key columns and additional context columns that help identify the duplicates."
                if is_multi_table:
                    special_case_instructions += "\nFor this MULTI-TABLE query: Fully qualify ALL column names with table names and include explicit join conditions."
                
                # Append special case instructions to the question if needed
                enhanced_question = question
                if special_case_instructions:
                    enhanced_question = f"{question}\n{special_case_instructions}"
                
                formatted_prompt = multi_sql_prompt.format(schema=schema, question=enhanced_question)
                
                payload = {
                    "anthropic_version": "bedrock-2023-05-31",
                    "max_tokens": 9000,  # Increased token limit for multiple queries
                    "temperature": self.temperature,
                    "system": self.system_prompt,
                    "messages": [
                        {
                            "role": "user",
                            "content": formatted_prompt
                        }
                    ]
                }
                
                response = self.bedrock_client.invoke_model(
                    modelId=self.model_id,
                    body=json.dumps(payload)
                )
                  
                # Parse the response
                response_body = json.loads(response['body'].read().decode('utf-8'))
                
                if 'content' not in response_body:
                    raise Exception(f"Unexpected response format: {response_body}")
                    
                raw_content = response_body['content'][0]['text']
                
                # Process completed successfully, break out of retry loop
                break
                
            except Exception as e:
                retry_count += 1
                if retry_count > max_retries:
                    # We've exhausted our retries, raise the exception
                    raise Exception(f"Error generating multiple SQL queries: {str(e)}")
        
        # Split the response by the separator
        raw_queries = raw_content.split("---QUERY_SEPARATOR---")
        
        # Clean each query
        clean_queries = []
        for raw_query in raw_queries:
            # Remove code block markers
            clean_query = raw_query.replace("```sql", "").replace("```", "").strip()
            
            # Remove any explanatory text before actual SQL
            if "WITH" in clean_query:
                clean_query = clean_query[clean_query.find("WITH"):]
            elif "SELECT" in clean_query:
                clean_query = clean_query[clean_query.find("SELECT"):]
            
            # Remove comments and clean up the query
            clean_lines = []
            for line in clean_query.split("\n"):
                # Remove inline comments
                if "--" in line:
                    line = line.split("--")[0]
                # Remove /* */ style comments
                if "/*" in line and "*/" in line:
                    line = line[:line.find("/*")] + line[line.find("*/") + 2:]
                line = line.strip()
                if line:  # only keep non-empty lines
                    clean_lines.append(line)
              # Join lines and ensure semicolon at the end
            final_query = " ".join(clean_lines).strip()
            if not final_query.endswith(";"):
                final_query += ";"
            clean_queries.append(final_query)
        
        return clean_queries


def execute_multi_query(conn, queries: List[str]) -> Dict[str, pd.DataFrame]:
    """Execute multiple SQL queries and return results as a dictionary of DataFrames.
    
    Args:
        conn: SQLite connection object
        queries (List[str]): List of SQL queries to execute
        
    Returns:
        Dict[str, pd.DataFrame]: Dictionary mapping query index to result DataFrame
        
    Raises:
        Exception: If there's an error executing any query
    """
    results = {}
    errors = {}
    
    for i, query in enumerate(queries):
        try:
            # Use a descriptive key for the results dictionary
            key = f"query_{i+1}"
            
            # Handle PRAGMA queries specially
            if query.upper().startswith("PRAGMA"):
                cursor = conn.cursor()
                cursor.execute(query)
                columns = [desc[0] for desc in cursor.description]
                data = cursor.fetchall()
                results[key] = pd.DataFrame(data, columns=columns)
            else:                # Regular SQL query
                df = pd.read_sql_query(query, conn)
                
                # Fix duplicate column names with a completely robust approach
                if any(df.columns.duplicated()):
                    # Create a list to store new unique column names
                    new_columns = []
                    seen_columns = {}
                    
                    # Process each column, adding suffixes to duplicates
                    for col in df.columns:
                        if col in seen_columns:
                            # Increment the count for this column name
                            seen_columns[col] += 1
                            # Add the count as a suffix
                            new_col = f"{col}_{seen_columns[col]}"
                            
                            # Handle the case where the new column name is still a duplicate
                            while new_col in new_columns or new_col in seen_columns:
                                seen_columns[col] += 1
                                new_col = f"{col}_{seen_columns[col]}"
                                
                            new_columns.append(new_col)
                        else:
                            # First occurrence of this column name
                            seen_columns[col] = 0
                            new_columns.append(col)
                    
                    # Apply the new column names to the DataFrame
                    df.columns = new_columns
                
                results[key] = df
                
            # Add the query text to the results for reference
            results[key].attrs['query_text'] = query
            
        except Exception as e:
            error_msg = f"Error executing query: {str(e)}"
            errors[f"query_{i+1}"] = {
                "error_message": error_msg,
                "query_text": query
            }
    
    # If we have any errors, add them to the results dictionary
    if errors:
        error_data = []
        for query_index, error_info in errors.items():
            error_data.append({
                "query_index": query_index,
                "error_message": error_info["error_message"],
                "query_text": error_info["query_text"]
            })
        results["errors"] = pd.DataFrame(error_data)    
    return results


def execute_query(conn, query: str) -> pd.DataFrame:
    """Execute SQL query and return results as a DataFrame."""
    try:
        return pd.read_sql_query(query, conn)
    except Exception as e:
        raise Exception(f"Error executing query: {str(e)}")


def analyze_multi_query_results(results: Dict[str, pd.DataFrame]) -> str:
    """
    Generate a comprehensive analysis of multiple query results.
    
    Args:
        results (Dict[str, pd.DataFrame]): Dictionary of query results
        
    Returns:
        str: Analysis of the query results
    """
    bedrock_client = boto3.client(
        service_name='bedrock-runtime',
        region_name=os.getenv('AWS_DEFAULT_REGION')
    )
    
    # Prepare the results summary
    results_summary = {}
    
    # Check if there were any errors
    if "errors" in results:
        results_summary["errors"] = results["errors"].to_dict(orient='records')
    
    # Process each query result
    for key, df in results.items():
        if key == "errors":
            continue
            
        # Extract the query text if available
        query_text = df.attrs.get('query_text', 'No query text available')
        
        # Create a summary for each DataFrame
        results_summary[key] = {
            "query_text": query_text,
            "shape": df.shape,
            "columns": list(df.columns)
        }
        
        if not df.empty:
            # Add sample data (limited to prevent token overflow)
            sample_rows = min(5, len(df))
            results_summary[key]["sample_data"] = df.head(sample_rows).to_dict(orient='records')
            
            # Add missing values analysis
            null_counts = df.isnull().sum()
            missing_data = {}
            for col, count in null_counts.items():
                if count > 0:
                    missing_data[col] = {
                        "null_count": int(count),
                        "percentage": float(round((count / len(df)) * 100, 2))
                    }
            results_summary[key]["missing_values"] = missing_data
            
            # Add basic statistics for numeric columns
            numeric_cols = df.select_dtypes(include=['int64', 'float64']).columns
            if not numeric_cols.empty:
                # Only include the most relevant statistics to save tokens
                stats = ['count', 'mean', 'min', 'max']
                results_summary[key]["numeric_summary"] = df[numeric_cols].describe().loc[stats].to_dict()
            
            # Add distribution information for categorical columns (limited to top values)
            cat_cols = df.select_dtypes(include=['object', 'category']).columns
            if not cat_cols.empty:
                cat_summary = {}
                for col in cat_cols[:3]:  # Limit to first 3 categorical columns
                    if df[col].nunique() <= 10:  # Only analyze columns with limited unique values
                        value_counts = df[col].value_counts().head(5).to_dict()
                        cat_summary[col] = value_counts
                if cat_summary:
                    results_summary[key]["categorical_summary"] = cat_summary
    
    # Prepare prompt for LLM
    prompt = f"""
    Analyze the following results from multiple SQL queries:
    
    {json.dumps(results_summary, indent=2)}
    
    Provide a comprehensive analysis that:
    1. Summarizes the key findings from each query
    2. Identifies any patterns in missing data across tables
    3. Highlights important statistics and distributions
    4. Notes any anomalies or outliers in the data
    5. Explains any errors that occurred and suggests possible fixes
    6. Provides an overall assessment of data quality
    
    Format your response in a clear, structured way with sections for each query result.
    If a query was looking for missing data, clearly indicate which columns have the most missing values.
    """
    
    # Prepare the payload for Claude
    payload = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 3000,
        "temperature": 0.2,
        "system": "You are an expert data analyst who creates comprehensive analyses of SQL query results. Focus on highlighting key patterns, missing data issues, and data quality concerns.",
        "messages": [
            {
                "role": "user",
                "content": prompt
            }
        ]
    }
    
    try:
        # Call the Bedrock API
        response = bedrock_client.invoke_model(
            modelId='us.anthropic.claude-sonnet-4-20250514-v1:0',
            body=json.dumps(payload)
        )
        
        # Parse the response
        response_body = json.loads(response['body'].read().decode('utf-8'))
        analysis = response_body['content'][0]['text']
        return analysis
        
    except Exception as e:
        return f"Error generating analysis: {str(e)}"

def generate_protocol_summary(df: pd.DataFrame, study_name: str = None) -> str:
    """
    Generate a summary of DataFrame results according to a protocol file.
    
    Args:
        df (pd.DataFrame): The DataFrame containing query results
        study_name (str): The name of the study to get protocol files from
        
    Returns:
        str: A summary that follows the protocol guidelines or fallback analysis
    """
    # Define paths to protocol files (study-specific first, then global)
    if study_name:
        protocol_dir = os.path.join(os.getcwd(), "studies", study_name, "protocols")
    else:
        protocol_dir = os.path.join(os.getcwd(), "protocols")
    
    protocol_file_path = os.path.join(protocol_dir, "protocol.pdf")
    annotation_file_path = os.path.join(protocol_dir, "annotation.pdf")
    
    # Check if study-specific protocol exists, fallback to global if not
    has_protocol = os.path.exists(protocol_file_path)
    if not has_protocol and study_name:
        # Try global protocol directory as fallback
        protocol_dir = os.path.join(os.getcwd(), "protocols")
        protocol_file_path = os.path.join(protocol_dir, "protocol.pdf")
        annotation_file_path = os.path.join(protocol_dir, "annotation.pdf")
        has_protocol = os.path.exists(protocol_file_path)
    
    # If no protocol file exists, use fallback analysis
    if not has_protocol:
        # Create basic DataFrame analysis for fallback
        df_summary = {
            "shape": df.shape,
            "columns": list(df.columns),
            "dtypes": {col: str(dtype) for col, dtype in df.dtypes.items()},
            "missing_values": df.isnull().sum().to_dict()
        }
        
        # Include sample data
        if df.shape[0] <= 100:
            df_summary["sample_data"] = df.head(20).to_dict(orient='records')
        else:
            df_summary["sample_data"] = df.head(10).to_dict(orient='records')
        
        # Create fallback prompt for basic analysis
        prompt = f"""
        Analyze the following dataset without any protocol guidance. Provide a CONCISE summary with exactly 5 key bullet points:
        
        {json.dumps(df_summary, indent=2)}
        
        Start your summary with: "Based on the data analysis, here are the key findings from this dataset:"
        
        Provide EXACTLY 5 bullet points. Each bullet point should be one sentence conveying a specific, actionable insight backed by data.
        Format each bullet point on a separate line starting with '• ' (bullet space).
        """
        
        # Use AWS Bedrock for fallback analysis
        bedrock_client = boto3.client(
            service_name='bedrock-runtime',
            region_name=os.getenv('AWS_DEFAULT_REGION')
        )
        
        payload = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 600,
            "temperature": 0.1,
            "system": "You are an expert data analyst who creates concise, precise summaries. Provide exactly 5 bullet points with key insights. Focus on the most important findings with specific numbers. Be direct and actionable.",
            "messages": [{"role": "user", "content": prompt}]
        }
        
        try:
            response = bedrock_client.invoke_model(
                modelId='anthropic.claude-3-5-sonnet-20240620-v1:0',
                body=json.dumps(payload)
            )
            response_body = json.loads(response['body'].read().decode('utf-8'))
            return response_body['content'][0]['text']
        except Exception as e:
            return f"Error generating fallback summary: {str(e)}"
    
    # Read protocol file - handling PDF specifically
    try:
        protocol_content = ""
        # Check if it's a PDF file
        if protocol_file_path.endswith('.pdf'):
            protocol_content = read_pdf_content(protocol_file_path)
        else:
            # If it's a text file
            with open(protocol_file_path, 'r', encoding='utf-8', errors='ignore') as f:
                protocol_content = f.read()
    except Exception as e:
        return f"Error reading protocol file: {str(e)}"
    
    # Read annotation file if it exists
    annotation_content = ""
    if os.path.exists(annotation_file_path):
        try:
            if annotation_file_path.endswith('.pdf'):
                annotation_content = read_pdf_content(annotation_file_path)
            else:
                with open(annotation_file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    annotation_content = f.read()
        except Exception as e:
            return f"Error reading annotation file: {str(e)}"    # Create a representation of the DataFrame - use hybrid approach based on size
    df_summary = {
        "shape": df.shape,
        "columns": list(df.columns),
        "dtypes": {col: str(dtype) for col, dtype in df.dtypes.items()},
        "missing_values": df.isnull().sum().to_dict(),
        "numeric_summary": df.describe().to_dict() if not df.select_dtypes(include=['number']).empty else {},
        # For categorical columns, limit to top 5 values to save tokens
        "categorical_summary": {
            col: df[col].value_counts().head(5).to_dict() 
            for col in df.select_dtypes(include=['object', 'category']).columns
        }
    }
    
    # Check DataFrame size against threshold (300 rows x 9 columns)
    # Only include all rows if DataFrame is smaller than the threshold
    if df.shape[0] <= 300 and df.shape[1] <= 9:
        # DataFrame is small enough, include all rows
        df_summary["all_rows"] = df.to_dict(orient='records')
        df_summary["data_completeness"] = "full"
    else:
        # DataFrame is too large, include just a sample of rows
        df_summary["sample_rows"] = df.head(50).to_dict(orient='records')
        df_summary["data_completeness"] = "partial"
      # Use the full protocol content without truncation
    protocol_sample = protocol_content
      # Add annotation information if available
    annotation_section = ""
    if annotation_content:
        # Process annotation content to extract mappings
        processed_annotations = process_annotation_content(annotation_content)
        # Use the full annotation content without truncation
        annotation_sample = annotation_content
            
        annotation_section = f"""
    
    IMPORTANT - Term to Database Column Mappings:
    The annotation file provides mappings between common terms and database column names.
    When analyzing data, translate between database column names and their common terms.
    
    {processed_annotations["mapping_examples"]}
    
    Full Annotation Reference:
    {annotation_sample}
    """      # Prepare prompt for LLM
    prompt = f"""
    Based on the following protocol guidelines (sample):
    
    {protocol_sample}{annotation_section}
    
    And given this data summary:
    
    {json.dumps(df_summary, indent=2)}
    
    IMPORTANT: The data you are analyzing represents a FILTERED SUBSET of the original dataset, not the complete study population. When interpreting results and calculating percentages, always consider this context.
    
    Begin with a brief introduction to the data, then provide a CONCISE protocol-based summary that:
    1. Focuses ONLY on significant findings (<5 key points)
    2. Uses direct, precise language with minimal explanation
    3. Highlights clear patterns, outliers, and critical insights
    4. Quantifies findings with specific numbers/percentages
    5. Organizes information in a structured, scannable format

    Note: For larger datasets, you have access to sample rows and complete statistics rather than the full dataset.
    Note: {"You have access to the complete dataset." if df_summary.get("data_completeness") == "full" else "Due to the size of the dataset, you have access to a partial sample of the data along with complete statistics."}

    Start your summary with: "Based on the provided data summary and protocol requirements, here are the key findings:"

    DO NOT include methodological explanations, or tentative language.
    Each sentence should convey a specific, actionable insight backed by data while acknowledging the subset context.
    """
  
    
    # Use existing AWS Bedrock client
    bedrock_client = boto3.client(
        service_name='bedrock-runtime',
        region_name=os.getenv('AWS_DEFAULT_REGION')
    )    # Prepare the payload for Claude
    payload = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 2000,
        "temperature": 0,
        "system": "You are an expert data analyst who creates summaries following strict protocols and understands specialized terminology. Analyze the data provided along with its statistics to create a thorough and accurate summary.",
        "messages": [
            {
                "role": "user",
                "content": prompt
            }
        ]
    }
    
    try:
        # Call the Bedrock API directly
        response = bedrock_client.invoke_model(
            modelId='anthropic.claude-3-5-sonnet-20240620-v1:0',
            body=json.dumps(payload)
        )
        
        # Parse the response
        response_body = json.loads(response['body'].read().decode('utf-8'))
        summary = response_body['content'][0]['text']
        return summary
        
    except Exception as e:
        return f"Error generating summary: {str(e)}"

def get_table_schema(conn) -> str:
    """Get the schema of all tables in the database."""
    schema_info = []
    
    cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = cursor.fetchall()
    
    for table in tables:
        table_name = table[0]
        cursor.execute(f"PRAGMA table_info({table_name})")
        columns = cursor.fetchall()
        
        schema_info.append(f"Table: {table_name}")
        for col in columns:
            schema_info.append(f"  - {col[1]} ({col[2]})")
        schema_info.append("")
    
    return "\n".join(schema_info)

def generate_multi_query_protocol_summary(results_dict: Dict[str, pd.DataFrame], study_name: str = None) -> str:
    """
    Generate a summary of multiple query results according to a protocol file.
    
    Args:
        results_dict (Dict[str, pd.DataFrame]): Dictionary of DataFrames from multiple queries
        study_name (str): The name of the study to get protocol files from
        
    Returns:
        str: A summary that follows the protocol guidelines or fallback analysis
    """
    # Define paths to protocol files (study-specific first, then global)
    if study_name:
        protocol_dir = os.path.join(os.getcwd(), "studies", study_name, "protocols")
    else:
        protocol_dir = os.path.join(os.getcwd(), "protocols")
    
    protocol_file_path = os.path.join(protocol_dir, "protocol.pdf")
    annotation_file_path = os.path.join(protocol_dir, "annotation.pdf")
    
    # Check if study-specific protocol exists, fallback to global if not
    has_protocol = os.path.exists(protocol_file_path)
    if not has_protocol and study_name:
        # Try global protocol directory as fallback
        protocol_dir = os.path.join(os.getcwd(), "protocols")
        protocol_file_path = os.path.join(protocol_dir, "protocol.pdf")
        annotation_file_path = os.path.join(protocol_dir, "annotation.pdf")
        has_protocol = os.path.exists(protocol_file_path)
    
    # If no protocol file exists, use fallback analysis
    if not has_protocol:
        # Create basic analysis for all query results
        results_summary = {}
        
        for key, df in results_dict.items():
            if key == "errors":
                continue
            
            results_summary[key] = {
                "shape": df.shape,
                "columns": list(df.columns),
                "dtypes": {col: str(dtype) for col, dtype in df.dtypes.items()},
                "sample_data": df.head(10).to_dict(orient='records') if not df.empty else []
            }
        
        # Create fallback prompt for multi-query analysis
        prompt = f"""
        Analyze the following results from multiple SQL queries without any protocol guidance. Provide a CONCISE summary with exactly 5 key bullet points:
        
        {json.dumps(results_summary, indent=2)}
        
        Start your summary with: "Based on the analysis of multiple query results, here are the comprehensive findings:"
        
        Provide EXACTLY 5 bullet points. Each bullet point should be one sentence conveying a specific, actionable insight backed by data.
        Format each bullet point on a separate line starting with '• ' (bullet space).
        """
        
        # Use AWS Bedrock for fallback analysis
        bedrock_client = boto3.client(
            service_name='bedrock-runtime',
            region_name=os.getenv('AWS_DEFAULT_REGION')
        )
        
        payload = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 600,
            "temperature": 0.1,
            "system": "You are an expert data analyst who creates concise, precise summaries. Provide exactly 5 bullet points with key insights from multiple query results. Focus on the most important cross-query findings with specific numbers. Be direct and actionable.",
            "messages": [{"role": "user", "content": prompt}]
        }
        
        try:
            response = bedrock_client.invoke_model(
                modelId='anthropic.claude-3-5-sonnet-20240620-v1:0',
                body=json.dumps(payload)
            )
            response_body = json.loads(response['body'].read().decode('utf-8'))
            return response_body['content'][0]['text']
        except Exception as e:
            return f"Error generating fallback multi-query summary: {str(e)}"
    
    # Read protocol file - handling PDF specifically
    try:
        protocol_content = ""
        # Check if it's a PDF file
        if protocol_file_path.endswith('.pdf'):
            protocol_content = read_pdf_content(protocol_file_path)
        else:
            # If it's a text file
            with open(protocol_file_path, 'r', encoding='utf-8', errors='ignore') as f:
                protocol_content = f.read()
    except Exception as e:
        return f"Error reading protocol file: {str(e)}"
    
    # Read annotation file if it exists
    annotation_content = ""
    if os.path.exists(annotation_file_path):
        try:
            if annotation_file_path.endswith('.pdf'):
                annotation_content = read_pdf_content(annotation_file_path)
            else:
                with open(annotation_file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    annotation_content = f.read()
        except Exception as e:
            return f"Error reading annotation file: {str(e)}"      # Use the full protocol content without truncation
    protocol_sample = protocol_content
      # Add annotation information if available
    annotation_section = ""
    if annotation_content:
        # Process annotation content to extract mappings
        processed_annotations = process_annotation_content(annotation_content)
        # Use the full annotation content without truncation
        annotation_sample = annotation_content
            
        annotation_section = f"""
    
    IMPORTANT - Term to Database Column Mappings:
    The annotation file provides mappings between common terms and database column names.
    When analyzing data, translate between database column names and their common terms.
    
    {processed_annotations["mapping_examples"]}
    
    Full Annotation Reference:
    {annotation_sample}
    """
    
    # Create a compact representation of all DataFrames in the results dictionary
    results_summary = {}
    
    # Process each query result, excluding errors
    for key, df in results_dict.items():
        if key == "errors":
            continue
            
        # Extract the query text if available
        query_text = df.attrs.get('query_text', 'No query text available')        # Create a summary for each DataFrame
        results_summary[key] = {
            "query_text": query_text,
            "shape": df.shape,
            "columns": list(df.columns),
            "dtypes": {col: str(dtype) for col, dtype in df.dtypes.items()},
            "missing_values": df.isnull().sum().to_dict()
        }
        
        if not df.empty:
            # Check DataFrame size against threshold (300 rows x 9 columns)
            # Only include all rows if DataFrame is smaller than the threshold
            if df.shape[0] <= 300 and df.shape[1] <= 9:
                # DataFrame is small enough, include all rows
                results_summary[key]["all_rows"] = df.to_dict(orient='records')
                results_summary[key]["data_completeness"] = "full"
            else:
                # DataFrame is too large, include just a sample of rows
                results_summary[key]["sample_rows"] = df.head(50).to_dict(orient='records')
                results_summary[key]["data_completeness"] = "partial"
            
            # Add basic statistics for numeric columns
            numeric_cols = df.select_dtypes(include=['int64', 'float64']).columns
            if not numeric_cols.empty:
                # Only include the most relevant statistics to save tokens
                stats = ['count', 'mean', 'min', 'max']
                try:
                    results_summary[key]["numeric_summary"] = df[numeric_cols].describe().loc[stats].to_dict()
                except:
                    pass  # Skip if there's an issue with generating stats
            
            # Add distribution information for categorical columns (limited to top values)
            cat_cols = df.select_dtypes(include=['object', 'category']).columns
            if not cat_cols.empty:
                cat_summary = {}
                for col in cat_cols[:3]:  # Limit to first 3 categorical columns
                    if df[col].nunique() <= 10:  # Only analyze columns with limited unique values
                        value_counts = df[col].value_counts().head(5).to_dict()
                        cat_summary[col] = value_counts
                if cat_summary:
                    results_summary[key]["categorical_summary"] = cat_summary    # Prepare prompt for LLM
    prompt = f"""
    Based on the following protocol guidelines (sample):
    
    {protocol_sample}{annotation_section}
    
    And given this summary of multiple query results:
    
    {json.dumps(results_summary, indent=2)}

    IMPORTANT: The data you are analyzing represents a FILTERED SUBSET of the original dataset, not the complete study population. When interpreting results and calculating percentages, always consider this context.
    
    Begin with a brief introduction to the data, then provide a CONCISE protocol-based summary that:
    1. Focuses ONLY on significant findings (<5 key points)
    2. Uses direct, precise language with minimal explanation
    3. Highlights clear patterns, outliers, and critical insights
    4. Quantifies findings with specific numbers/percentages
    5. Organizes information in a structured, scannable format

    Note: For larger datasets, you have access to sample rows and complete statistics rather than the full dataset.

    Start your summary with: "Based on the provided data summary and protocol requirements, here are the key findings:"

    DO NOT include methodological explanations, or tentative language.
    Each sentence should convey a specific, actionable insight backed by data while acknowledging the subset context.
    """
    
    # Use existing AWS Bedrock client
    bedrock_client = boto3.client(
        service_name='bedrock-runtime',
        region_name=os.getenv('AWS_DEFAULT_REGION')
    )    # Prepare the payload for Claude
    payload = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 2000,
        "temperature": 0.2,
        "system": "You are an expert data analyst who creates summaries following strict protocols and understands specialized terminology. You must translate between database column names and their common terms using the annotation file provided. For multi-query results, provide an integrated analysis based on the available data and statistics.",
        "messages": [
            {
                "role": "user",
                "content": prompt
            }
        ]
    }
    
    try:
        # Call the Bedrock API directly
        response = bedrock_client.invoke_model(
            modelId='anthropic.claude-3-5-sonnet-20240620-v1:0',
            body=json.dumps(payload)
        )
        
        # Parse the response
        response_body = json.loads(response['body'].read().decode('utf-8'))
        summary = response_body['content'][0]['text']
        return summary
        
    except Exception as e:
        return f"Error generating protocol summary for multi-query results: {str(e)}"


def generate_visualization_code(df: pd.DataFrame, user_question: str) -> Dict[str, str]:
    """
    Generate Python/Plotly visualization code using LLM based on DataFrame and user question.
    
    Args:
        df (pd.DataFrame): The DataFrame to visualize
        user_question (str): The user's question/request for visualization
        
    Returns:
        Dict[str, str]: Dictionary containing 'code', 'description', and 'error' (if any)
    """
    try:
        # Create a comprehensive DataFrame summary for the LLM
        df_summary = {
            "shape": df.shape,
            "columns": list(df.columns),
            "dtypes": {col: str(dtype) for col, dtype in df.dtypes.items()},
            "missing_values": df.isnull().sum().to_dict(),
            "column_analysis": {}
        }
        
        # Analyze each column in detail
        for col in df.columns:
            col_info = {
                "type": str(df[col].dtype),
                "unique_count": int(df[col].nunique()),
                "null_count": int(df[col].isnull().sum())
            }
            
            # Add statistics based on column type
            if df[col].dtype in ['int64', 'float64']:
                col_info["numeric_stats"] = {
                    "min": float(df[col].min()) if not df[col].empty else None,
                    "max": float(df[col].max()) if not df[col].empty else None,
                    "mean": float(df[col].mean()) if not df[col].empty else None
                }
            elif df[col].dtype == 'object' or df[col].dtype.name == 'category':
                # For categorical data, show top values
                if df[col].nunique() <= 20:  # Only show if reasonable number of categories
                    col_info["top_values"] = df[col].value_counts().head(10).to_dict()
            
            df_summary["column_analysis"][col] = col_info
        
        # Include sample data if DataFrame is small enough
        if df.shape[0] <= 100:
            df_summary["sample_data"] = df.head(10).to_dict(orient='records')
        else:
            df_summary["sample_data"] = df.head(5).to_dict(orient='records')
        
        # Prepare the LLM prompt
        prompt = f"""
You are an expert data visualization specialist. Based on the user's question and the DataFrame analysis below, generate Python code using Plotly to create the most appropriate visualization(s).

User Question: {user_question}

DataFrame Analysis:
{json.dumps(df_summary, indent=2)}

REQUIREMENTS:
1. Generate ONLY executable Python code using pandas and plotly.express
2. Assume the DataFrame is already available as variable 'df'
3. Create visualizations that directly answer the user's question
4. Use appropriate chart types based on data types and relationships
5. Include meaningful titles, axis labels, and formatting
6. Handle potential data issues (missing values, outliers) gracefully
7. If multiple visualizations would be helpful, create them
8. Return the final plotly figure object as 'fig'

IMPORTANT GUIDELINES:
- For categorical data: Use bar charts, pie charts, or count plots
- For numeric data: Use histograms, scatter plots, box plots, or line charts
- For time series: Use line charts with proper date formatting
- For correlations: Use scatter plots or heatmaps
- For distributions: Use histograms or box plots
- For comparisons: Use bar charts or grouped visualizations

CODE STRUCTURE:
- Import required libraries (import plotly.express as px, import pandas as pd)
- Create the visualization using the df DataFrame
- Assign the final figure to variable 'fig'
- Add appropriate titles and labels
- Handle any data preprocessing needed

EXAMPLE OUTPUT FORMAT:
```python
import plotly.express as px
import pandas as pd

# Data preprocessing if needed
df_viz = df.copy()

# Create visualization
fig = px.bar(df_viz, x='column1', y='column2', title='Meaningful Title')
fig.update_layout(xaxis_title='X Label', yaxis_title='Y Label')
```

Generate the visualization code:
"""
        
        # Use existing AWS Bedrock client
        bedrock_client = boto3.client(
            service_name='bedrock-runtime',
            region_name=os.getenv('AWS_DEFAULT_REGION')
        )
        
        # Prepare the payload for Claude
        payload = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 2000,
            "temperature": 0.1,
            "system": "You are an expert data visualization specialist who generates clean, executable Python code using Plotly. Always return only the Python code needed to create the visualization, without explanations or markdown formatting.",
            "messages": [
                {
                    "role": "user",
                    "content": prompt
                }
            ]
        }
        
        # Call the Bedrock API
        response = bedrock_client.invoke_model(
            modelId='us.anthropic.claude-sonnet-4-20250514-v1:0',
            body=json.dumps(payload)
        )
        
        # Parse the response
        response_body = json.loads(response['body'].read().decode('utf-8'))
        raw_code = response_body['content'][0]['text']
        
        # Clean the code - remove markdown code blocks if present
        if "```python" in raw_code:
            code = raw_code.split("```python")[1].split("```")[0].strip()
        elif "```" in raw_code:
            code = raw_code.split("```")[1].strip()
        else:
            code = raw_code.strip()
        
        # Generate a description for the visualization
        description = f"LLM-generated visualization based on: {user_question}"
        
        return {
            "code": code,
            "description": description,
            "error": None
        }
        
    except Exception as e:
        return {
            "code": None,
            "description": None,
            "error": f"Error generating visualization code: {str(e)}"
        }


def execute_visualization_code(code: str, df: pd.DataFrame) -> Dict[str, any]:
    """
    Execute the LLM-generated visualization code safely.
    
    Args:
        code (str): Python code to execute
        df (pd.DataFrame): DataFrame to use in the code
        
    Returns:
        Dict[str, any]: Dictionary containing 'fig' (plotly figure) and 'error' (if any)
    """
    try:
        # Create a safe execution environment
        import plotly.express as px
        import plotly.graph_objects as go
        import pandas as pd
        import numpy as np
        from datetime import datetime, timedelta
        
        # Prepare the execution environment with commonly used functions
        exec_globals = {
            'pd': pd,
            'px': px,
            'go': go,
            'np': np,
            'df': df.copy(),  # Provide a copy to avoid modifying original
            'fig': None,
            'datetime': datetime,
            'timedelta': timedelta,
            # Add common functions that might be needed
            'len': len,
            'str': str,
            'int': int,
            'float': float,
            'list': list,
            'dict': dict,
            'sum': sum,
            'max': max,
            'min': min,
            'round': round
        }
        
        # Additional safety: restrict potentially dangerous operations
        restricted_names = ['__import__', 'eval', 'exec', 'open', 'file', 'input', 'raw_input']
        for name in restricted_names:
            if name in code:
                return {
                    "fig": None,
                    "error": f"Code contains restricted operation: {name}"
                }
        
        # Execute the code
        exec(code, exec_globals)
        
        # Get the figure from the execution environment
        fig = exec_globals.get('fig')
        
        if fig is None:
            return {
                "fig": None,
                "error": "Generated code did not create a 'fig' variable"
            }
        
        # Validate that it's a plotly figure
        if not hasattr(fig, 'to_html'):
            return {
                "fig": None,
                "error": "Generated 'fig' is not a valid plotly figure"
            }
        
        return {
            "fig": fig,
            "error": None
        }
        
    except Exception as e:
        return {
            "fig": None,
            "error": f"Error executing visualization code: {str(e)}"
        }


def generate_conversational_response(question_text: str, context: dict = None) -> str:
    """
    Generate a conversational response using AWS Bedrock Claude for general chat interactions.
    
    Args:
        question_text (str): The user's question or message
        context (dict, optional): Additional context for the conversation
        
    Returns:
        str: LLM-generated conversational response
    """
    try:
        # Set up AWS Bedrock client
        bedrock_client = boto3.client(
            service_name='bedrock-runtime',
            region_name=os.getenv('AWS_DEFAULT_REGION')
        )
        
        # Build context information
        context_info = ""
        if context:
            context_info = f"\nContext information:\n{json.dumps(context, indent=2)}\n"
        
        # Create the prompt
        prompt = f"""You are a helpful AI assistant for a data review application. Respond in a friendly, conversational manner.

{context_info}

User message: {question_text}

Please provide a helpful, friendly response. Keep it conversational and concise. If the user is asking about studies or data analysis, provide guidance based on the context provided.
"""
        
        # Prepare the payload for Claude
        payload = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 500,
            "temperature": 0.7,
            "system": "You are a friendly, helpful AI assistant for a data review application. Respond conversationally and keep responses concise but informative.",
            "messages": [
                {
                    "role": "user", 
                    "content": prompt
                }
            ]
        }
        
        # Call the Bedrock API
        response = bedrock_client.invoke_model(
            modelId='us.anthropic.claude-sonnet-4-20250514-v1:0',
            body=json.dumps(payload)
        )
        
        # Parse the response
        response_body = json.loads(response['body'].read().decode('utf-8'))
        return response_body['content'][0]['text'].strip()
        
    except Exception as e:
        # Fallback response if LLM fails
        return "I'm here to help! Let me know what you'd like to do - whether it's working with existing studies, creating new ones, or analyzing your data."


def handle_conversation_context(question_text: str) -> str:
    """
    Handle conversation context and workflow for study creation and general chat.
    
    Args:
        question_text (str): User's input text
        
    Returns:
        str: Response text for the user
    """
    import streamlit as st
    from tools.db_utils import DatabaseConnection
    
    # Get current conversation mode
    conversation_mode = st.session_state.get('conversation_mode', 'normal')
    
    # Handle different conversation modes
    if conversation_mode == 'awaiting_study_name':
        return handle_study_name_input(question_text)
        
    elif conversation_mode == 'awaiting_protocol_upload':
        return handle_protocol_upload_prompt(question_text)
        
    elif conversation_mode == 'awaiting_data_upload':
        return handle_data_upload_prompt(question_text)
        
    elif conversation_mode == 'normal':
        # Check for new study creation intent
        intent_result = detect_chat_intent(question_text)
        
        if intent_result.get('intent') == 'study_management' and intent_result.get('parameters', {}).get('action') == 'create':
            # Start study creation workflow with interface uploaders
            st.session_state.workflow_step = 'create_study_name'
            st.session_state.conversation_mode = 'normal'  # Use interface workflow, not conversation mode
            return "🎯 **Let's create a new study!**\n\nThe study name input will appear below this chat. Please enter a descriptive name for your new study."
        
        # FALLBACK: Manual pattern matching for study creation if LLM fails
        create_patterns = [
            'create new study', 'new study', 'make new study', 'start new study',
            'create a study', 'make a study', 'start a study', 'work on new study',
            'working on new study', 'i want to create', 'want to create new'
        ]
        
        if any(pattern in question_text.lower() for pattern in create_patterns):
            st.session_state.workflow_step = 'create_study_name'
            st.session_state.conversation_mode = 'normal'  # Use interface workflow, not conversation mode
            return "🎯 **Let's create a new study!**\n\nThe study name input will appear below this chat. Please enter a descriptive name for your new study."
        
        else:
            # Generate general conversational response
            context = {
                'available_studies': DatabaseConnection.list_available_studies(),
                'current_study': st.session_state.get('current_study'),
                'intent': intent_result.get('intent', 'chat')
            }
            return generate_conversational_response(question_text, context)
    
    else:
        # Unknown conversation mode - reset to normal
        st.session_state.conversation_mode = 'normal'
        return "Let me help you! What would you like to do?"


def handle_study_name_input(study_name: str) -> str:
    """Handle study name input during study creation workflow."""
    import streamlit as st
    import os
    
    # Clean the study name
    study_name = study_name.strip()
    
    if not study_name:
        return "❌ Please provide a valid study name. What would you like to name your study?"
    
    # Check if study already exists
    existing_studies = [d for d in os.listdir("studies") if os.path.isdir(os.path.join("studies", d))] if os.path.exists("studies") else []
    
    if study_name in existing_studies:
        return f"❌ A study named '{study_name}' already exists. Please choose a different name."
    
    # Store the study name and move directly to protocol upload interface
    st.session_state.pending_study_name = study_name
    st.session_state.workflow_step = 'upload_protocol'
    st.session_state.conversation_mode = 'normal'  # Reset to normal so interface workflow takes over
    
    return f"✅ **Study name set: '{study_name}'**\n\n� **Step 1: Protocol Upload (Optional)**\n\nThe protocol uploader will appear below. You can upload a PDF protocol file or skip to data upload."


def handle_protocol_upload_prompt(user_input: str) -> str:
    """Handle protocol upload confirmation during study creation workflow."""
    import streamlit as st
    
    user_input = user_input.lower().strip()
    
    if user_input in ['done', 'uploaded', 'finished', 'complete']:
        st.session_state.workflow_step = 'upload_data'
        st.session_state.conversation_mode = 'normal'  # Reset to normal so interface workflow takes over
        return "✅ **Protocol uploaded successfully!**\n\n📊 **Step 2: Data Upload**\n\nThe data uploader will appear below. Upload your CSV or Excel files to complete the study setup."
        
    elif user_input in ['skip', 'no', 'cancel']:
        st.session_state.workflow_step = 'upload_data'
        st.session_state.conversation_mode = 'normal'  # Reset to normal so interface workflow takes over
        return "⏭️ **Skipping protocol upload.**\n\n📊 **Step 2: Data Upload**\n\nThe data uploader will appear below. Upload your CSV or Excel files to complete the study setup."
        
    else:
        return "📁 Please upload your protocol file using the uploader below, then type **'done'** when finished, or type **'skip'** to proceed to data upload."


def handle_data_upload_prompt(user_input: str) -> str:
    """Handle data upload confirmation during study creation workflow."""
    import streamlit as st
    
    user_input = user_input.lower().strip()
    
    if user_input in ['done', 'uploaded', 'finished', 'complete']:
        return complete_study_creation_and_switch()
        
    elif user_input in ['skip', 'no', 'cancel']:
        return complete_study_creation_and_switch()
        
    else:
        return "📊 Please upload your data files using the uploader below, then type **'done'** to complete your study setup."


def complete_study_creation_and_switch() -> str:
    """Complete study creation process and switch to study interface if data is ready."""
    import streamlit as st
    import os
    from tools.db_utils import DatabaseConnection, get_current_db_connection
    from tools.data_tools import load_column_mappings
    
    study_name = st.session_state.get('pending_study_name')
    
    if not study_name:
        st.session_state.conversation_mode = 'normal'
        return "❌ Error: No study name found. Please start the study creation process again."
    
    try:
        # Create study directories if they don't exist
        if not DatabaseConnection.create_study_directories(study_name):
            raise Exception("Failed to create study directories")
        
        # Create the database connection for the new study
        db_path = os.path.join("studies", study_name, "data", "app.db")
        
        # Check if the study has data tables (database should exist if data was uploaded)
        if os.path.exists(db_path):
            # Switch to the new study
            st.session_state.current_study = study_name
            
            # Reinitialize database and related components
            current_db = get_current_db_connection()
            st.session_state.tables = current_db.list_tables()
            
            # Load column mappings for this study
            load_column_mappings(study_name)
            
            # Create chat history for the new study
            table_count = len(st.session_state.tables) if st.session_state.tables else 0
            st.session_state.chat_histories[study_name] = [
                (None, f"🎉 **Welcome to your new study '{study_name}'!**"),
                (None, f"📊 Successfully created with {table_count} data tables." if table_count > 0 else "📊 Study created but no data tables found."),
                (None, "🚀 **Your study is ready for analysis!** What would you like to explore first?")
            ]
            
            # Sync to new study's chat
            from tools.data_tools import sync_chat_history
            sync_chat_history()
            
            # Clear workflow state
            st.session_state.conversation_mode = 'normal'
            st.session_state.pending_study_name = None
            st.session_state.workflow_step = None
            
            # NOW switch to the study interface since everything is ready
            st.session_state.show_welcome_screen = False
            
            return f"✅ **Study '{study_name}' created successfully!** You are now working in this study. I can help you analyze your {table_count} data tables. What would you like to explore?"
        
        else:
            # Study created but no data uploaded yet
            st.session_state.conversation_mode = 'normal'
            st.session_state.pending_study_name = None
            
            return f"📁 Study '{study_name}' directories created, but no data was uploaded yet. Please upload your data files using the sidebar, then we can complete the study setup."
    
    except Exception as e:
        st.session_state.conversation_mode = 'normal'
        st.session_state.pending_study_name = None
        return f"❌ Error creating study '{study_name}': {str(e)}"


def handle_workflow_steps(question_text):
    """Handle multi-step workflows based on current workflow step - simplified to not change interface"""
    import streamlit as st
    
    # This function is kept for compatibility but most logic moved to handle_conversation_context
    return handle_conversation_context(question_text)