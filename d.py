import tkinter as tk
from tkinter import scrolledtext, messagebox
import requests
import json
import threading

# --- API Functions ---

def get_free_dictionary_definition(word):
    """
    Fetches definition from the free Dictionary API (dictionaryapi.dev).
    This is the primary API as it doesn't require an API key.
    """
    try:
        response = requests.get(f"https://api.dictionaryapi.dev/api/v2/entries/en/{word}")
        response.raise_for_status()  # Raise an exception for bad status codes (4xx or 5xx)
        data = response.json()
        
        definitions = []
        if isinstance(data, list) and data:
            for entry in data:
                for meaning in entry.get('meanings', []):
                    part_of_speech = meaning.get('partOfSpeech', 'N/A')
                    for definition_info in meaning.get('definitions', []):
                        definition = definition_info.get('definition', 'No definition found.')
                        example = definition_info.get('example', '')
                        def_str = f"({part_of_speech}) {definition}"
                        if example:
                            def_str += f"\n  - Example: \"{example}\""
                        definitions.append(def_str)
        return "\n".join(definitions) if definitions else "No definition found for this word."
    except requests.exceptions.HTTPError as http_err:
        if http_err.response.status_code == 404:
            return "Word not found in this dictionary."
        else:
            return f"HTTP error occurred: {http_err}"
    except requests.exceptions.RequestException as e:
        return f"An error occurred: {e}"
    except json.JSONDecodeError:
        return "Could not parse the response from the server."

def get_llm_definition(word, callback):
    """
    Crafts a prompt and fetches a definition and example from a Gemini LLM.
    This function is designed to be run in a separate thread to avoid freezing the GUI.
    """
    try:
        prompt = f"Provide a clear and concise definition for the word '{word}', followed by an example sentence showing its usage. Don't use markdown syntax."
        
        api_url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-preview-05-20:generateContent"
        api_key = "" # In a collaborative environment, this key is automatically provided.

        headers = {'Content-Type': 'application/json'}
        payload = {
            "contents": [{
                "parts": [{"text": prompt}]
            }]
        }
        full_api_url = f"{api_url}?key={api_key}"
        
        response = requests.post(full_api_url, headers=headers, json=payload)
        response.raise_for_status() # Will raise an exception for HTTP error codes
        
        result = response.json()
        
        # Safely parse the response to find the generated text
        if (result.get('candidates') and 
            isinstance(result['candidates'], list) and
            len(result['candidates']) > 0 and
            result['candidates'][0].get('content') and 
            result['candidates'][0]['content'].get('parts') and
            isinstance(result['candidates'][0]['content']['parts'], list) and
            len(result['candidates'][0]['content']['parts']) > 0 and
            result['candidates'][0]['content']['parts'][0].get('text')):
            
            response_text = result['candidates'][0]['content']['parts'][0]['text']
            callback(response_text)
        else:
            # If the response structure is unexpected, show an error with the raw response
            error_message = f"Error: Unexpected API response format.\n\nRaw response:\n{json.dumps(result, indent=2)}"
            callback(error_message)

    except requests.exceptions.HTTPError as http_err:
        # Show detailed HTTP error, including the response body if available
        callback(f"An HTTP error occurred: {http_err}\nResponse: {http_err.response.text}")
    except requests.exceptions.RequestException as e:
        # Show network-related errors
        callback(f"A network error occurred while contacting the LLM: {e}")
    except (KeyError, IndexError, TypeError) as e:
        # Show errors related to parsing the JSON response
        callback(f"Error parsing the LLM response: {e}")
    except Exception as e:
        # Catch any other unexpected errors
        callback(f"An unexpected error occurred: {e}")


# --- GUI Application ---

class DictionaryApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Multi-Source English Dictionary")
        self.root.geometry("700x550")
        self.root.configure(bg='#f0f0f0')
        self.create_widgets()

    def create_widgets(self):
        # --- Main Frame ---
        main_frame = tk.Frame(self.root, bg='#f0f0f0', padx=15, pady=15)
        main_frame.pack(expand=True, fill=tk.BOTH)

        # --- Input Frame ---
        input_frame = tk.Frame(main_frame, bg='#f0f0f0')
        input_frame.pack(fill=tk.X, pady=(0, 10))

        tk.Label(input_frame, text="Enter a word:", font=("Helvetica", 12), bg='#f0f0f0').pack(side=tk.LEFT, padx=(0, 10))
        
        self.word_entry = tk.Entry(input_frame, font=("Helvetica", 12), width=30)
        self.word_entry.pack(side=tk.LEFT, expand=True, fill=tk.X)
        self.word_entry.bind("<Return>", self.search_word) # Bind Enter key to search

        self.search_button = tk.Button(input_frame, text="Search", command=self.search_word, font=("Helvetica", 11, "bold"), bg="#4a90e2", fg="white", relief=tk.FLAT, padx=10)
        self.search_button.pack(side=tk.LEFT, padx=(10, 0))

        # --- Results Display ---
        self.results_text = scrolledtext.ScrolledText(main_frame, wrap=tk.WORD, font=("Helvetica", 11), state='disabled', bg='white', relief=tk.SOLID, borderwidth=1)
        self.results_text.pack(expand=True, fill=tk.BOTH)

    def search_word(self, event=None):
        """Fetches and displays definitions for the entered word."""
        word = self.word_entry.get().strip()
        if not word:
            messagebox.showwarning("Input Error", "Please enter a word to search.")
            return

        self.results_text.config(state='normal')
        self.results_text.delete('1.0', tk.END)
        
        # --- Get definition from the free dictionary API ---
        self.add_result_header("Free Dictionary (dictionaryapi.dev)")
        definition1 = get_free_dictionary_definition(word)
        self.results_text.insert(tk.END, definition1 + "\n\n")

        # --- Get definition from the LLM ---
        self.add_result_header("LLM Definition (Gemini)")
        self.results_text.insert(tk.END, "Fetching definition from LLM... Please wait.\n")
        
        # Run the LLM request in a separate thread to keep the GUI responsive
        threading.Thread(target=get_llm_definition, args=(word, self.update_llm_result), daemon=True).start()
        
    def update_llm_result(self, result):
        """Callback function to update the GUI with the LLM result."""
        # Ensure GUI updates are done in the main thread
        self.root.after(0, self._insert_llm_result, result)

    def _insert_llm_result(self, result):
        """Helper function to insert text into the widget from the main thread."""
        self.results_text.config(state='normal')
        # Find and replace the "Fetching..." message
        start_index = self.results_text.search("Fetching definition from LLM...", "1.0", tk.END)
        if start_index:
            end_index = f"{start_index} + 1 lines"
            self.results_text.delete(start_index, end_index)
            self.results_text.insert(start_index, result + "\n\n")
        else: # Fallback if message not found
            self.results_text.insert(tk.END, result + "\n\n")

        self.results_text.config(state='disabled')
        
    def add_result_header(self, title):
        """Formats and adds a header to the results text area."""
        self.results_text.insert(tk.END, f"--- {title} ---\n", 'header')
        self.results_text.tag_config('header', font=('Helvetica', 12, 'bold'), foreground='#333')

if __name__ == "__main__":
    root = tk.Tk()
    app = DictionaryApp(root)
    root.mainloop()
