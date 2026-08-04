export type Message = {
  id: string;
  sender: 'user' | 'bot';
  text: string;
  files?: File[];
};