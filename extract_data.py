#Edits python scripts to get information, edit, or add information from an excel sheet using the openpyxl library. Uses excel_notes.txt to understand the excel sheet. 
from aider.coders import Coder
from aider.models import Model
from aider.io import InputOutput

class AiderRunner:
    def __init__(self, file_name , user_prompt):
        self.fname = file_name
        self.user_prompt = user_prompt
        self.coder = None

    def setup_coder(self) -> Coder:
        model = Model("claude-3-5-sonnet-20240620")
        io = InputOutput(yes=True, chat_history_file="testing_aider.txt")
        self.coder = Coder.create(
                main_model=model,
                io=io,
                fnames=[self.fname],
                read_only_fnames=["excel_notes.txt"],
                stream=False,
                use_git=False,
                edit_format="diff",
            )

        return self.coder

    def run(self):   
        coder = self.setup_coder()
        instruction = f"Use the openpyxl library and not pandas to do the following with the excel spreadsheet: {self.user_prompt}"
        result = coder.run(instruction)
        return result


def main():

    # Create an instance of AiderRunner with the custom input function
    runner = AiderRunner("hello_excel_1.py", "Get a list of classes available on friday.")
    runner.run()

if __name__ == "__main__":
    main()
