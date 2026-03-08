import React from "react";
import { BiEdit } from "react-icons/bi";
import Image from "next/image";

const basePath = process.env.NEXT_PUBLIC_BASE_PATH || "";

export const Icon = ({ source }: { source: string }) => {
  return (
    <div className="w-4 h-4 rounded-full bg-zinc-700 flex items-center justify-center overflow-hidden -mr-1">
      <Image src={`${basePath}${source}`} alt={source} width={40} height={40} />
    </div>
  );
};

export const constants = {
  claude: {
    name: "Claude",
    icon: <Icon source="/images/claude.webp" />,
    iconImage: `${basePath}/images/claude.webp`,
  },
  openmemory: {
    name: "OpenMemory",
    icon: <Icon source="/images/open-memory.svg" />,
    iconImage: `${basePath}/images/open-memory.svg`,
  },
  cursor: {
    name: "Cursor",
    icon: <Icon source="/images/cursor.png" />,
    iconImage: `${basePath}/images/cursor.png`,
  },
  cline: {
    name: "Cline",
    icon: <Icon source="/images/cline.png" />,
    iconImage: `${basePath}/images/cline.png`,
  },
  roocline: {
    name: "Roo Cline",
    icon: <Icon source="/images/roocline.png" />,
    iconImage: `${basePath}/images/roocline.png`,
  },
  windsurf: {
    name: "Windsurf",
    icon: <Icon source="/images/windsurf.png" />,
    iconImage: `${basePath}/images/windsurf.png`,
  },
  witsy: {
    name: "Witsy",
    icon: <Icon source="/images/witsy.png" />,
    iconImage: `${basePath}/images/witsy.png`,
  },
  enconvo: {
    name: "Enconvo",
    icon: <Icon source="/images/enconvo.png" />,
    iconImage: `${basePath}/images/enconvo.png`,
  },
  augment: {
    name: "Augment",
    icon: <Icon source="/images/augment.png" />,
    iconImage: `${basePath}/images/augment.png`,
  },
  default: {
    name: "Default",
    icon: <BiEdit size={18} className="ml-1" />,
    iconImage: `${basePath}/images/default.png`,
  },
};

const SourceApp = ({ source }: { source: string }) => {
  if (!constants[source as keyof typeof constants]) {
    return (
      <div>
        <BiEdit />
        <span className="text-sm font-semibold">{source}</span>
      </div>
    );
  }
  return (
    <div className="flex items-center gap-2">
      {constants[source as keyof typeof constants].icon}
      <span className="text-sm font-semibold">
        {constants[source as keyof typeof constants].name}
      </span>
    </div>
  );
};

export default SourceApp;
