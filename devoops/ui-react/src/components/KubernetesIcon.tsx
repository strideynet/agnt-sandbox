import { SiKubernetes } from 'react-icons/si';

interface KubernetesIconProps {
  className?: string;
  size?: number;
}

export function KubernetesIcon({ className = '', size = 20 }: KubernetesIconProps) {
  return (
    <SiKubernetes
      className={className}
      size={size}
      color="#326CE5"
    />
  );
}
