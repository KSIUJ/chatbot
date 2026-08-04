import facadeImage from "../../assets/facade_4-Dwl60qUz.svg";

export default function LoginBackground() {
  return (
    <div className="absolute top-1/2 left-0 w-full -translate-y-1/2 opacity-30 pointer-events-none select-none flex justify-center">
      <div 
        className="w-full max-w-7xl bg-blue-900" 
        style={{
          WebkitMaskImage: `url(${facadeImage})`,
          WebkitMaskSize: 'contain',
          WebkitMaskRepeat: 'no-repeat',
          WebkitMaskPosition: 'center',
          maskImage: `url(${facadeImage})`,
          maskSize: 'contain',
          maskRepeat: 'no-repeat',
          maskPosition: 'center'
        }}
      >
        <img src={facadeImage} alt="Fasada" className="w-full opacity-0" />
      </div>
    </div>
  );
}