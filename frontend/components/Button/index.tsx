import { PropsWithChildren } from "react";

const Button = (props: PropsWithChildren<{onClick?: () => void, className?: string, disabled?: boolean}>) => {
    return (
        <button
            onClick={props.onClick}
            disabled={props.disabled}
            className={`relative ${props.className || ""} py-2 px-3 rounded-lg font-medium text-sm bg-gradient-to-b from-[#190d2e] to-[#4a208a] shadow-[0px_0px_12px_#8c45ff] ${props.disabled ? 'opacity-50 cursor-not-allowed' : ''}`}
        >
            <div className="absolute inset-0">
                <div className="rounded-lg border border-white/20 absolute inset-0 [mask-image:linear-gradient(to_bottom,black,transparent)]"></div>
                <div className="rounded-lg border absolute inset-0 border-white/40 [mask-image:linear-gradient(to_bottom,black,transparent)]"></div>
                <div className="absolute inset-0 shadow-[0_0_10px_rgb(140,69,255,.7)_inset] rounded-lg"></div>
            </div>
            <span>
                {props.children}
            </span>
        </button>
    );
};

export default Button;