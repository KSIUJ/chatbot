// One chat bubble. Messages from the server have no status; "stopped" and
// "error" are local markers shown with a retry button.
export type ChatMessage = {
  id: string;
  sender: 'user' | 'bot';
  text: string;
  status?: 'stopped' | 'error';
};
